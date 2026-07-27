"""Observabilidade — lista traces do provider ativo + link pra UI completa.

**Langfuse é o primário; LangSmith é o fallback.** Quando `LANGFUSE_ENABLED`
(as duas keys setadas), a lista vem do Langfuse self-host; senão cai pro
LangSmith (`LANGCHAIN_API_KEY/PROJECT`). 503 só quando NENHUM está configurado.

A UI não duplica o painel do provider: traz uma lista resumida (nome, status,
latência, tokens, thread) + `Abrir →` que leva pro trace na UI do provider.
Filtro por `thread_id` mapeia pra `session_id` no Langfuse (o worker seta
`session_id = thread_id`) e pra `extra.metadata.thread_id` no LangSmith.
"""

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from langsmith import Client as LangSmithClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared import langfuse_client
from whatsapp_langchain.shared.app_setting import (
    CHAVE_OBS_PROVIDER,
    OBS_PROVIDER_VALIDOS,
    get_obs_provider_preferido,
    set_setting,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import TraceInfo

logger = structlog.get_logger()

# Teto que a API do LangSmith impõe por request em POST /runs/query. Acima
# disso ela devolve 400 "Limit exceeds maximum allowed value of 100".
LANGSMITH_MAX_LIMIT = 100

router = APIRouter(
    prefix="/api/traces",
    tags=["traces"],
    dependencies=[Depends(verify_service_token)],
)


def _langfuse_configurado() -> bool:
    return settings.langfuse_enabled


def _langsmith_configurado() -> bool:
    return bool(settings.langchain_api_key and settings.langchain_project)


def _active_provider() -> str | None:
    """Resolução automática: langfuse > langsmith > None."""
    if _langfuse_configurado():
        return "langfuse"
    if _langsmith_configurado():
        return "langsmith"
    return None


async def _provider_efetivo() -> str | None:
    """Provider a usar, considerando a preferência gravada na UI (mig 141).

    Existe porque a resolução por env é uma armadilha operacional: desligar os
    containers do Langfuse NÃO muda `settings.langfuse_enabled` (as chaves
    seguem no .env), então `/traces` continuaria apontando pro host morto.

    `auto` mantém o comportamento antigo. Escolha explícita que aponta pra
    provider sem credencial cai no automático em vez de devolver nada — o
    admin vê a lista do outro provider, não uma tela vazia sem explicação.
    """
    pool = await get_pool()
    preferido = await get_obs_provider_preferido(pool)

    if preferido == "langfuse" and _langfuse_configurado():
        return "langfuse"
    if preferido == "langsmith" and _langsmith_configurado():
        return "langsmith"

    if preferido != "auto":
        logger.warning(
            "obs_provider_preferido_sem_credencial",
            preferido=preferido,
            acao="caindo pra resolucao automatica",
        )
    return _active_provider()


# ----------------------------- Langfuse ------------------------------


def _lf_to_trace_info(t: dict[str, Any]) -> TraceInfo:
    tid = str(t.get("id"))
    latency = t.get("latency")  # segundos (float) no Langfuse
    latency_ms = int(latency * 1000) if isinstance(latency, int | float) else None
    usage = t.get("usage") or {}
    total_tokens = usage.get("total") if isinstance(usage, dict) else None
    url = langfuse_client.trace_url(tid)
    return TraceInfo(
        run_id=tid,
        name=t.get("name"),
        status=None,
        start_time=t.get("timestamp"),
        end_time=None,
        latency_ms=latency_ms,
        total_tokens=total_tokens,
        thread_id=t.get("sessionId"),
        source="langfuse",
        url=url,
        smith_url=url,
    )


# ----------------------------- LangSmith -----------------------------


def _smith_url(run_id: str) -> str:
    return (
        f"https://smith.langchain.com/o/_/projects/p/"
        f"{settings.langchain_project}/r/{run_id}"
    )


def _to_trace_info(run) -> TraceInfo:
    metadata = (run.extra or {}).get("metadata", {}) or {}
    latency_ms = None
    if run.end_time and run.start_time:
        latency_ms = int((run.end_time - run.start_time).total_seconds() * 1000)

    url = _smith_url(str(run.id))
    return TraceInfo(
        run_id=str(run.id),
        name=run.name,
        status=run.status,
        start_time=run.start_time.isoformat() if run.start_time else None,
        end_time=run.end_time.isoformat() if run.end_time else None,
        latency_ms=latency_ms,
        total_tokens=run.total_tokens,
        thread_id=metadata.get("thread_id"),
        source="langsmith",
        url=url,
        smith_url=url,
    )


def _fetch_runs(api_key: str, project: str, limit: int) -> list:
    """Bloqueia chamando a API LangSmith — chamado via asyncio.to_thread."""
    client = LangSmithClient(api_key=api_key)
    return list(
        client.list_runs(
            project_name=project,
            is_root=True,
            limit=limit,
        )
    )


@router.get("/config")
async def traces_config() -> dict[str, Any]:
    """Fonte ativa + o que o switch da UI precisa pra montar as opções.

    `preferido` é o que está gravado (pode ser `auto`); `provider` é o que
    vale de fato depois de checar credencial. Os dois diferem quando alguém
    escolhe um provider sem chave configurada.
    """
    pool = await get_pool()
    preferido = await get_obs_provider_preferido(pool)
    provider = await _provider_efetivo()
    return {
        "provider": provider,
        "enabled": provider is not None,
        "preferido": preferido,
        "disponiveis": {
            "langfuse": _langfuse_configurado(),
            "langsmith": _langsmith_configurado(),
        },
    }


@router.put("/config")
async def set_traces_config(
    body: dict[str, Any],
    empresa_id: int = Depends(get_empresa_context),  # noqa: ARG001 — só autentica
    # Preferência é GLOBAL (infra compartilhada), então exige permissão de
    # integração — mesma usada em conexao.py e integracoes_api.py. Sem isto o
    # invariante `test_no_new_mutator_endpoints_without_permission_dep` acusa,
    # e com razão: qualquer membro trocaria a observabilidade de todo mundo.
    _perm: None = Depends(require_permission("integracao.manage")),
) -> dict[str, Any]:
    """Troca o provider de observabilidade pela UI, sem redeploy.

    Aceita provider sem credencial de propósito: o admin pode preparar a
    troca antes de subir o outro stack. O `/config` deixa a divergência
    visível (`preferido` != `provider`).
    """
    escolhido = str(body.get("provider") or "").strip().lower()
    if escolhido not in OBS_PROVIDER_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"provider inválido: {escolhido or '(vazio)'}",
        )
    pool = await get_pool()
    await set_setting(pool, CHAVE_OBS_PROVIDER, escolhido, updated_by="painel")
    provider = await _provider_efetivo()
    return {"preferido": escolhido, "provider": provider}


@router.get("/atendimento/{atendimento_id}")
async def trace_link_for_atendimento(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Deep-link de observabilidade pra um atendimento.

    Resolve o `thread_id` EXATO (`phone_number:agent_id`) da última mensagem do
    atendimento na `message_queue` — garante match com o `session_id` no
    Langfuse. Retorna também a URL direta do trace quando há `langfuse_trace_id`.
    """
    provider = await _provider_efetivo()
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT phone_number, agent_id, langfuse_trace_id "
            "FROM message_queue "
            "WHERE empresa_id = %s AND atendimento_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (empresa_id, atendimento_id),
        )
        row = await cur.fetchone()
    if row is None:
        return {"provider": provider, "thread_id": None, "trace_url": None}
    phone, agent, trace_id = row
    thread_id = f"{phone}:{agent}" if phone and agent else None
    trace_url = (
        langfuse_client.trace_url(trace_id)
        if trace_id and settings.langfuse_enabled
        else None
    )
    return {"provider": provider, "thread_id": thread_id, "trace_url": trace_url}


async def _empresa_thread_ids(
    empresa_id: int, thread_id: str | None
) -> set[str] | None:
    """`thread_id`s (`phone:agent`) que pertencem à empresa, via `message_queue`.

    Escopo multi-tenant OBRIGATÓRIO: o store de observabilidade (Langfuse/
    LangSmith) é único por instância, então sem este filtro o endpoint vazaria
    traces — e os telefones de cliente embutidos no `thread_id` — de OUTROS
    tenants. Quando um `thread_id` específico é pedido, valida o pertencimento e
    retorna `None` (→ resposta vazia) se não for da empresa.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        if thread_id is not None:
            cur = await conn.execute(
                "SELECT 1 FROM message_queue "
                "WHERE empresa_id = %s AND phone_number || ':' || agent_id = %s "
                "LIMIT 1",
                (empresa_id, thread_id),
            )
            return {thread_id} if await cur.fetchone() else None
        cur = await conn.execute(
            "SELECT DISTINCT phone_number || ':' || agent_id "
            "FROM message_queue "
            "WHERE empresa_id = %s "
            "AND phone_number IS NOT NULL AND agent_id IS NOT NULL",
            (empresa_id,),
        )
        return {r[0] for r in await cur.fetchall()}


@router.get("")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    thread_id: str | None = Query(default=None),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[TraceInfo]]:
    """Lista traces recentes do provider ativo (Langfuse > LangSmith), ESCOPADOS
    pela empresa do usuário.

    Só retorna traces cujo `thread_id` (`phone:agent`) pertence à empresa — o
    store é global por instância, então filtrar por tenant é obrigatório pra não
    vazar dados (incl. telefones) de outras empresas.
    """
    provider = await _provider_efetivo()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Observabilidade não configurada (defina LANGFUSE_* ou "
                "LANGCHAIN_API_KEY/PROJECT)."
            ),
        )

    allowed = await _empresa_thread_ids(empresa_id, thread_id)
    if not allowed:
        return {"traces": []}

    # Busca uma janela maior e filtra pelos thread_ids da empresa (os N mais
    # recentes do store podem pertencer a outros tenants).
    fetch = min(limit * 5, 500)

    if provider == "langfuse":
        raw = await asyncio.to_thread(langfuse_client.list_traces, fetch, thread_id)
        traces = [_lf_to_trace_info(t) for t in raw]
        traces = [t for t in traces if t.thread_id in allowed][:limit]
        logger.debug(
            "traces_listed", provider=provider, count=len(traces), empresa_id=empresa_id
        )
        return {"traces": traces}

    # Fallback LangSmith — filtro client-side.
    #
    # O over-fetch acima (limit*5) é o que o Langfuse aceita, mas a API do
    # LangSmith recusa `limit` > 100:
    #   400 {"detail":"Limit exceeds maximum allowed value of 100"}
    # Com limit=50 o cálculo pedia 250 e a página inteira quebrava. Não era
    # visível antes porque o Langfuse era sempre o primário e este ramo nunca
    # executava.
    #
    # Consequência aceita: com muitos tenants ativos, 100 runs podem render
    # menos de `limit` traces da empresa depois do filtro. Melhor lista curta
    # que erro 500.
    api_key = settings.langchain_api_key.get_secret_value()  # type: ignore[union-attr]
    project = settings.langchain_project
    fetch_smith = min(fetch, LANGSMITH_MAX_LIMIT)
    runs = await asyncio.to_thread(_fetch_runs, api_key, project, fetch_smith)
    traces = [_to_trace_info(r) for r in runs]
    traces = [t for t in traces if t.thread_id in allowed][:limit]
    logger.debug(
        "traces_listed", provider=provider, count=len(traces), empresa_id=empresa_id
    )
    return {"traces": traces}
