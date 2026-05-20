"""CRUD de Atendimentos do painel admin (M3 CRM Light).

A lista é paginada por **tipo de visualização** (`meus`, `aguardando`,
`grupos`, `outros`) — derivado em runtime, sem coluna no banco. As
mutações (`claim`, `close`, `transfer`) seguem o ciclo de vida descrito
em `shared/atendimento.py`.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.aba import (
    attach_atendimento_to_aba,
    count_atendimentos_por_aba,
)
from whatsapp_langchain.shared.atendimento import (
    claim_atendimento,
    close_atendimento,
    get_atendimento_by_id,
    list_atendimento_mensagens,
    list_atendimentos,
    transfer_atendimento,
    transfer_atendimento_to_departamento,
)
from whatsapp_langchain.shared.atendimento_tag import (
    apply_tags_to_atendimento,
    list_atendimento_ids_com_tags,
    list_tags_de_atendimento,
)
from whatsapp_langchain.shared.atendimento_visualizacao import marcar_lido
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_admin_of
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
from whatsapp_langchain.shared.models import Atendimento
from whatsapp_langchain.shared.nota_interna import create_nota_interna
from whatsapp_langchain.shared.outbound import OutboundError, send_outbound_manual
from whatsapp_langchain.shared.perfil import get_user_permissions
from whatsapp_langchain.shared.permissoes import (
    effective_scope,
    get_user_departamento_ids,
)
from whatsapp_langchain.shared.queue import reset_thread_checkpoint
from whatsapp_langchain.shared.variavel import build_render_context, render_template


async def _resolve_perms_cached(
    request: Request, user_id: str, empresa_id: int
) -> set[str]:
    """Cache de permissões por request — evita N queries quando handler
    chama effective_scope várias vezes."""
    cached = getattr(request.state, "_user_perms", None)
    if cached is not None:
        return cached
    pool = await get_pool()
    perms = await get_user_permissions(pool, user_id, empresa_id)
    request.state._user_perms = perms
    return perms


logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/atendimentos",
    tags=["atendimentos"],
    dependencies=[Depends(verify_service_token)],
)


TipoVisualizacao = Literal["meus", "aguardando", "grupos", "outros"]


class CloseInput(BaseModel):
    status: Literal["resolvido", "abandonado"] = "resolvido"


class TransferInput(BaseModel):
    """Aceita exatamente um destino: atendente (user_id) ou departamento."""

    user_id: str | None = None
    departamento_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> TransferInput:
        if bool(self.user_id) == bool(self.departamento_id):
            raise ValueError("Informe exatamente um: user_id OU departamento_id")
        return self


class ResponderInput(BaseModel):
    conteudo: str


class AttachAbaInput(BaseModel):
    """Atribuir/desatribuir aba (None desatribui)."""

    aba_id: int | None = None


class ApplyTagsInput(BaseModel):
    """Delta de tags em um atendimento."""

    add: list[int] = []
    remove: list[int] = []


class NotaInternaInput(BaseModel):
    """Texto de nota interna (msg privada na timeline da equipe)."""

    texto: str = Field(min_length=1, max_length=4000)


@router.get("")
async def list_my_atendimentos(
    request: Request,
    tipo: TipoVisualizacao = Query(default="aguardando"),
    dep_id: int | None = Query(default=None, ge=1),
    prioridade: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    aba_id: int | None = Query(default=None, ge=1),
    tag_id: list[int] | None = Query(
        default=None, description="Filter por tag(s) OR — multi-valor"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[Atendimento]]:
    """Lista atendimentos da empresa filtrados pelo tipo (4 abas) +
    filtros opcionais Sprint F.2: departamento, prioridade, busca em
    cliente.nome/atendimento.protocolo.

    Sprint Governança RBAC (mig 083): aplica filtro record-level baseado
    em `atendimento.read.own/all`. Operador (perm `.own`) só vê
    atendimentos do(s) depto(s) vinculado(s) a ele em
    `usuario_departamento`. Sem nenhuma das duas perms → 403.
    """
    if prioridade is not None and prioridade not in (
        "baixa",
        "media",
        "alta",
        "urgente",
    ):
        raise HTTPException(status_code=400, detail="prioridade inválida")
    pool = await get_pool()
    # Resolve scope record-level ANTES da query
    perms = await _resolve_perms_cached(request, user_id, empresa_id)
    scope = effective_scope(perms, "atendimento.read")
    if scope is None:
        raise HTTPException(
            status_code=403,
            detail="Permissão necessária: atendimento.read[.own|.all]",
        )
    scope_dept_ids: set[int] | None = None
    if scope == "own":
        dept_ids = await get_user_departamento_ids(pool, user_id, empresa_id)
        # Set vazio = sem deptos vinculados → list_atendimentos retorna []
        scope_dept_ids = set(dept_ids)

    # Filtro por tag (OR): resolve IDs de atendimentos que têm qualquer tag
    only_ids: list[int] | None = None
    if tag_id:
        only_ids = await list_atendimento_ids_com_tags(
            pool, empresa_id=empresa_id, tag_ids=tag_id
        )

    rows = await list_atendimentos(
        pool,
        empresa_id,
        tipo=tipo,
        current_user_id=user_id,
        limit=limit,
        offset=offset,
        dep_id=dep_id,
        prioridade=prioridade,
        q=q,
        aba_id=aba_id,
        only_ids=only_ids,
        scope_departamento_ids=scope_dept_ids,
    )
    return {"atendimentos": rows}


@router.get("/contadores")
async def list_contadores(
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Contadores pra badges da sidebar (sistema + abas do user).

    Usa as mesmas semânticas de scope record-level que `list_atendimentos`.
    Sem cache — query é leve (COUNT com index). Frontend chama a cada
    SSE event `aba_count_changed` (também a cada 30s como fallback).
    """
    pool = await get_pool()
    perms = await _resolve_perms_cached(request, user_id, empresa_id)
    scope = effective_scope(perms, "atendimento.read")
    if scope is None:
        # Sem perm: zero pra todos (sidebar fica vazia, não 403)
        return {
            "sistema": {
                "aguardando": 0,
                "meus": 0,
                "outros": 0,
            },
            "abas": {},
            "sem_aba": 0,
        }
    dept_filter_sql = ""
    dept_filter_args: list = []
    if scope == "own":
        dept_ids = await get_user_departamento_ids(pool, user_id, empresa_id)
        if not dept_ids:
            return {
                "sistema": {"aguardando": 0, "meus": 0, "outros": 0},
                "abas": {},
                "sem_aba": 0,
            }
        dept_filter_sql = " AND departamento_id = ANY(%s)"
        dept_filter_args = [list(dept_ids)]

    async with pool.connection() as conn:
        # Sistema (aguardando / meus / outros)
        cur = await conn.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE status = 'aguardando'),
                COUNT(*) FILTER (WHERE status = 'em_andamento'
                                  AND assigned_to_user_id = %s),
                COUNT(*) FILTER (WHERE status IN ('aguardando', 'em_andamento')
                                  AND (assigned_to_user_id IS NULL
                                       OR assigned_to_user_id <> %s))
              FROM atendimento
             WHERE empresa_id = %s{dept_filter_sql}
            """,
            (user_id, user_id, empresa_id, *dept_filter_args),
        )
        sys_row = await cur.fetchone() or (0, 0, 0)

        # Sem aba (pra "Não classificados" na sidebar)
        cur = await conn.execute(
            f"""
            SELECT COUNT(*)
              FROM atendimento
             WHERE empresa_id = %s
               AND status IN ('aguardando', 'em_andamento')
               AND aba_id IS NULL{dept_filter_sql}
            """,
            (empresa_id, *dept_filter_args),
        )
        sem_aba = (await cur.fetchone() or (0,))[0]

    # Contadores por aba (sempre do próprio user — abas são pessoais)
    por_aba = await count_atendimentos_por_aba(
        pool, user_id=user_id, empresa_id=empresa_id
    )
    return {
        "sistema": {
            "aguardando": sys_row[0],
            "meus": sys_row[1],
            "outros": sys_row[2],
        },
        "abas": {str(k): v for k, v in por_aba.items()},
        "sem_aba": sem_aba,
    }


async def _load_atendimento_in_empresa(
    atendimento_id: int, empresa_id: int
) -> Atendimento:
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    if atd.empresa_id != empresa_id:
        raise HTTPException(
            status_code=403, detail="Atendimento fora da empresa ativa."
        )
    return atd


@router.get("/{atendimento_id}")
async def read_atendimento(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Atendimento:
    """Detalhe — inclui cliente_nome/cliente_telefone via JOIN."""
    return await _load_atendimento_in_empresa(atendimento_id, empresa_id)


# ---- E2.E SSE ----


@router.get("/{atendimento_id}/events")
async def sse_events(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
):
    """Stream de eventos do atendimento via SSE.

    Substitui o polling 3s do AtendimentoDrawer. Backend ouve canal
    Postgres `atendimento_event` (alimentado por triggers da mig 035) e
    relay eventos cujo `atendimento_id` bate com o requested.

    Conexão dedicada (psycopg async standalone), fora do pool — LISTEN
    bloqueia a conexão pra outros usos. Heartbeat a cada 25s pra
    sobreviver ao Traefik (idle timeout default 60s).

    Frontend acessa via Next.js API route proxy (/api/sse/...) que
    adiciona Authorization + X-User-Id headers — EventSource nativo
    não suporta headers custom.
    """
    import asyncio
    import json

    import psycopg
    from fastapi.responses import StreamingResponse

    from whatsapp_langchain.shared.config import settings

    # Valida ANTES de abrir o stream (retorna 4xx imediato se acesso negado)
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)

    async def event_generator():
        try:
            async with await psycopg.AsyncConnection.connect(
                settings.database_url, autocommit=True
            ) as conn:
                await conn.execute("LISTEN atendimento_event")
                yield (
                    f"event: connected\n"
                    f"data: {json.dumps({'atendimento_id': atendimento_id})}\n\n"
                )

                # psycopg.notifies(timeout=N) retorna AsyncGenerator que
                # *termina* quando o timeout expira. Loop externo re-abre
                # o generator + emite heartbeat a cada ciclo (25s).
                while True:
                    async for notify in conn.notifies(timeout=25):
                        try:
                            payload = json.loads(notify.payload)
                        except (ValueError, TypeError):
                            continue
                        if payload.get("atendimento_id") != atendimento_id:
                            continue
                        evt_name = payload.get("event", "update")
                        yield f"event: {evt_name}\ndata: {notify.payload}\n\n"
                    yield ": heartbeat\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sse_atendimento_failed",
                atendimento_id=atendimento_id,
                error=str(exc),
            )
            yield (f"event: error\ndata: {json.dumps({'error': str(exc)[:200]})}\n\n")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{atendimento_id}/mensagens")
async def read_atendimento_mensagens(
    atendimento_id: int,
    limit: int = Query(default=200, ge=1, le=500),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Mensagens cronológicas do atendimento (ASC).

    Cobre só mensagens com `atendimento_id` preenchido — inbound antigas
    (anteriores ao M3) ficam fora; o histórico legado segue acessível
    pela rota `/api/chats/{phone}` se for preciso.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    mensagens = await list_atendimento_mensagens(
        pool, atendimento_id, empresa_id, limit=limit
    )
    return {"atendimento_id": atendimento_id, "mensagens": mensagens}


@router.post("/{atendimento_id}/claim")
async def claim(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Atendimento:
    """Operador "puxa" o atendimento — vira em_andamento + assigned=user.

    Sprint G.3 — valida capacidade: 409 se user já tem >= max_paralelos
    atendimentos abertos. Default max=5 (mig 062).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    # Capacidade — só checa se user NÃO está claim-ando o atendimento atual
    # (caso edge de re-claim de algo que ele já tem).
    from whatsapp_langchain.shared.atendente import (
        count_atendimentos_user_abertos,
        get_max_paralelos,
    )

    count = await count_atendimentos_user_abertos(pool, user_id, empresa_id)
    max_paralelos = await get_max_paralelos(pool, user_id)
    if count >= max_paralelos:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Você já está atendendo {count} de {max_paralelos} atendimentos. "
                "Encerre algum antes de assumir mais."
            ),
        )
    out = await claim_atendimento(pool, atendimento_id, user_id)
    if out is None:
        # Já foi fechado entre o load e o claim (race) — sinaliza conflito.
        raise HTTPException(
            status_code=409, detail="Atendimento já fechado, não pode ser claimed."
        )
    logger.info(
        "atendimento_claimed",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        user_id=user_id,
    )
    # Sprint E.3 — Mensagem auto ao cliente avisando que atendente assumiu
    # ("Você foi transferido para o atendente *X*"). Best-effort: erro
    # não bloqueia claim. Resolve nome via auth.user; fallback "atendente".
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                'SELECT name FROM auth."user" WHERE id = %s',
                (user_id,),
            )
            row = await cur.fetchone()
        nome_atendente = (row[0] if row else None) or "atendente"
        from whatsapp_langchain.shared.outbound import send_system_outbound

        await send_system_outbound(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            conteudo=(f"Você foi transferido para o atendente *{nome_atendente}*."),
            tag_user_id=f"system:claim:{user_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "claim_outbound_failed",
            atendimento_id=atendimento_id,
            error=str(exc),
        )
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.atendido",
        {
            "atendimento_id": atendimento_id,
            "assigned_to_user_id": user_id,
            "cliente_id": out.cliente_id,
        },
    )
    return out


@router.post("/{atendimento_id}/close")
async def close(
    atendimento_id: int,
    body: CloseInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Atendimento:
    """Fecha atendimento. status='resolvido' (default) ou 'abandonado'."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    out = await close_atendimento(pool, atendimento_id, status=body.status)
    if out is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    logger.info(
        "atendimento_closed",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        status=body.status,
        user_id=user_id,
    )
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.fechado",
        {
            "atendimento_id": atendimento_id,
            "status": body.status,
            "closed_by_user_id": user_id,
            "cliente_id": out.cliente_id,
        },
    )
    # Sprint Y fix: dispara CSAT se a empresa tiver csat_ativo=true.
    # Best-effort — falha aqui não bloqueia o close.
    if body.status == "resolvido":
        from whatsapp_langchain.shared.avaliacao import trigger_csat_se_ativo

        await trigger_csat_se_ativo(pool, empresa_id, atendimento_id)
    return out


@router.post("/{atendimento_id}/responder")
async def responder(
    atendimento_id: int,
    body: ResponderInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Envia mensagem manual do operador.

    O atendimento precisa estar `aguardando` ou `em_andamento`. A mensagem
    é persistida em message_queue como row outbound-only — aparece na
    timeline do drawer junto às mensagens do agente IA.

    Antes do envio, `{{empresa.*}}`, `{{cliente.*}}`, `{{data.*}}` e
    `{{var.*}}` são resolvidos server-side (M5.d) — operador pode digitar
    `Olá {{cliente.nome}}!` direto e o cliente recebe o texto final.
    """
    pool = await get_pool()
    ctx = await build_render_context(pool, empresa_id, atendimento_id=atendimento_id)
    rendered = render_template(body.conteudo, ctx)
    try:
        row = await send_outbound_manual(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            user_id=user_id,
            conteudo=rendered,
        )
    except OutboundError as e:
        # Mapeia para 4xx — erros lógicos (atendimento fechado, etc).
        msg = str(e)
        status_code = 409 if "fechado" in msg else 404 if "encontrad" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg) from e
    return {"mensagem": row}


@router.post("/{atendimento_id}/transfer")
async def transfer(
    atendimento_id: int,
    body: TransferInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Atendimento:
    """Transfere o atendimento — modo `user_id` (atribui a outro operador,
    mantém em_andamento) OU modo `departamento_id` (limpa atendente, volta
    pra status=aguardando = entra na fila do depto).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()

    departamento_nome: str | None = None
    if body.departamento_id is not None:
        out = await transfer_atendimento_to_departamento(
            pool, atendimento_id, body.departamento_id
        )
        if out is None:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT nome FROM departamento WHERE id = %s AND empresa_id = %s",
                (body.departamento_id, empresa_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Departamento não encontrado.")
        departamento_nome = row[0]

        # Notifica o cliente via WhatsApp — best-effort. Falha não bloqueia
        # a transferência (atendimento já foi atualizado no DB).
        try:
            await send_outbound_manual(
                pool,
                atendimento_id=atendimento_id,
                empresa_id=empresa_id,
                user_id=user_id,
                conteudo=(
                    f"Você foi transferido para o setor *{departamento_nome}*. "
                    "Em breve um atendente entrará em contato. 😊"
                ),
            )
        except OutboundError as exc:
            logger.warning(
                "transfer_notify_failed",
                atendimento_id=atendimento_id,
                empresa_id=empresa_id,
                departamento_id=body.departamento_id,
                error=str(exc),
            )
    else:
        assert body.user_id is not None  # validator garante
        out = await transfer_atendimento(pool, atendimento_id, body.user_id)
        if out is None:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado.")

    logger.info(
        "atendimento_transferred",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        from_user=user_id,
        to_user=body.user_id,
        to_departamento=body.departamento_id,
    )
    # Payload unificado entre tool (IA) e endpoint manual — mesmo schema.
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.transferido",
        {
            "atendimento_id": atendimento_id,
            "from_user_id": user_id,
            "to_user_id": body.user_id,
            "departamento_id": out.departamento_id,
            "departamento_nome": departamento_nome,
            "prioridade": out.prioridade,
            "classificacao": out.classificacao,
            "sentimento": out.sentimento,
            "resumo_ia": out.resumo_ia,
            "cliente_id": out.cliente_id,
            "cliente_nome": out.cliente_nome,
            "phone": out.cliente_telefone,
            "protocolo": out.protocolo,
            "motivo": None,
            "iniciado_por": "humano",
            "agente_slug": None,
        },
    )
    return out


@router.post("/{atendimento_id}/reset-thread")
async def reset_thread(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Apaga checkpoint LangGraph do thread (phone:agent_id) do atendimento.

    Útil quando o agente "decora" um pattern errado das últimas mensagens
    (ex: respondeu "não tenho info" sem chamar tool, e modelo passa a
    replicar). Limpar força próxima mensagem a começar do zero com prompt
    + tools atuais.

    Não toca em message_queue, conversations, langgraph.store nem
    cliente_memoria. Só admin da empresa pode executar.
    """
    pool = await get_pool()

    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Só admin pode resetar conversa.",
        )

    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")

    cliente = await get_cliente_by_id(pool, atd.cliente_id)
    if cliente is None or cliente.empresa_id != empresa_id:
        raise HTTPException(
            status_code=404, detail="Cliente do atendimento não encontrado."
        )

    rows_deleted = await reset_thread_checkpoint(
        pool, cliente.telefone, atd.agente_atual
    )

    logger.info(
        "thread_checkpoint_reset",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        actor_user_id=user_id,
        phone=cliente.telefone,
        agent_id=atd.agente_atual,
        rows_deleted=rows_deleted,
    )
    return {
        "ok": True,
        "rows_deleted": rows_deleted,
        "thread_id": f"{cliente.telefone}:{atd.agente_atual}",
    }


@router.get("/{atendimento_id}/tags")
async def list_tags_endpoint(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista tags aplicadas no atendimento + quem aplicou (humano/IA)."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    items = await list_tags_de_atendimento(
        pool, atendimento_id=atendimento_id, empresa_id=empresa_id
    )
    return {"items": items}


@router.post("/{atendimento_id}/tags")
async def apply_tags(
    atendimento_id: int,
    payload: ApplyTagsInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.tag.aplicar")),
) -> dict:
    """Aplica delta de tags (add/remove) num atendimento.

    Idempotente. Cada linha inserida em `atendimento_tag` registra
    `aplicado_por_user_id` pra audit. Tags de outras empresas são
    silenciosamente filtradas no INSERT (JOIN com `tag.empresa_id`).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    result = await apply_tags_to_atendimento(
        pool,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        add_tag_ids=payload.add,
        remove_tag_ids=payload.remove,
        aplicado_por_user_id=user_id,
        aplicado_por_ia=False,
    )
    return result


@router.post("/{atendimento_id}/nota")
async def criar_nota_interna_endpoint(
    atendimento_id: int,
    payload: NotaInternaInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.nota_interna.criar")),
) -> dict:
    """Cria nota interna na timeline do atendimento.

    A nota fica em message_queue com `interna=true` — aparece em
    GET /mensagens normalmente, mas worker NUNCA envia outbound
    (gate em shared/outbound.py + nunca enfileirada como queued).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    return await create_nota_interna(
        pool,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        user_id=user_id,
        texto=payload.texto.strip(),
    )


@router.post("/{atendimento_id}/marcar-lido")
async def marcar_lido_endpoint(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """UPSERT em atendimento_visualizacao (mig 052) — zera badge "nova".

    Sem perm explícita: qualquer user que pode ver o atendimento pode
    marcar como lido pra si próprio.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    await marcar_lido(pool, atendimento_id=atendimento_id, user_id=user_id)
    return {"ok": True}


@router.post("/{atendimento_id}/aba")
async def attach_aba(
    atendimento_id: int,
    payload: AttachAbaInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Atribui/desatribui aba pessoal a um atendimento (pinning).

    Aba é sempre do user logado — `attach_atendimento_to_aba` valida
    que `aba_id` pertence ao user. `aba_id=null` desatribui.

    Não exige `atendimento.write` — atribuir aba é organização pessoal,
    não mexe no conteúdo da conversa. Atendimento precisa estar visível
    pro user (RBAC.read aplicado via `_load_atendimento_in_empresa`).
    """
    # Garante que atendimento existe e é da empresa.
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    ok = await attach_atendimento_to_aba(
        pool,
        atendimento_id=atendimento_id,
        aba_id=payload.aba_id,
        user_id=user_id,
        empresa_id=empresa_id,
    )
    if not ok:
        # aba_id != None e não é do user — 404 pra não vazar existência
        raise HTTPException(
            status_code=404,
            detail="Aba não encontrada ou não pertence ao usuário.",
        )
    logger.info(
        "atendimento_aba_attached",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        aba_id=payload.aba_id,
        user_id=user_id,
    )
    return {"ok": True, "aba_id": payload.aba_id}
