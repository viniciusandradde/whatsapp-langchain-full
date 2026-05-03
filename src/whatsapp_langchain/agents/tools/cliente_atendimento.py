"""Ferramentas de operação sobre cliente/atendimento (M5.b.1).

8 tools que dão ao agente acesso ao CRM da empresa em tempo de
conversa. Todas extraem `empresa_id` + `atendimento_id` do
`runtime.config.configurable` (preenchido pelo worker em invoke_config).

Tools de leitura — `get_cliente_profile`, `get_cliente_history`,
`get_cliente_anotacoes` — usam o `atendimento_id` pra resolver o cliente
implícito. Tools de escrita exigem essa ligação também: agente NÃO pode
operar sobre cliente arbitrário (anti-tenant escape).

Tools de gestão de atendimento (`close_atendimento`, `transfer_to_human`)
mexem na linha do `atendimento_id` corrente — tipicamente no fim da
conversa quando o agente decide "resolvi" ou "preciso de humano".
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared.atendimento import (
    close_atendimento as _close_atendimento,
    get_atendimento_by_id,
    list_atendimentos_by_cliente,
)
from whatsapp_langchain.shared.cliente import (
    add_anotacao,
    add_tag,
    get_cliente_by_id,
    list_anotacoes,
    update_cliente_partial,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def _extract_runtime_config(runtime: Any) -> dict[str, Any]:
    """Lê o `configurable` dict do runtime LangGraph (igual aos outros tools)."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict):
                return cfg
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable
    return {}


def _extract_ids(runtime: Any) -> tuple[int | None, int | None]:
    cfg = _extract_runtime_config(runtime)
    empresa_id = cfg.get("empresa_id")
    atendimento_id = cfg.get("atendimento_id")
    try:
        empresa_id = int(empresa_id) if empresa_id is not None else None
    except (TypeError, ValueError):
        empresa_id = None
    try:
        atendimento_id = int(atendimento_id) if atendimento_id is not None else None
    except (TypeError, ValueError):
        atendimento_id = None
    return empresa_id, atendimento_id


def _extract_user_id(runtime: Any) -> str:
    """user_id agente = "agente:<agent_id>" pra distinguir de operadores."""
    cfg = _extract_runtime_config(runtime)
    return f"agente:{cfg.get('user_id') or 'desconhecido'}"


# --- Leitura ---


@tool
async def get_cliente_profile(
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Retorna dados estruturados do cliente atual (nome, telefone, email, doc, tags).

    Use quando precisar saber com quem está falando (ex: cumprimentar
    pelo nome, validar dados antes de criar pedido). Sempre prefira
    chamar essa tool a perguntar dados que talvez já estejam cadastrados.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto — não consigo identificar o cliente."
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    cliente = await get_cliente_by_id(pool, atd.cliente_id)
    if cliente is None:
        return "cliente não encontrado."
    parts = [
        f"id: {cliente.id}",
        f"telefone: {cliente.telefone}",
        f"nome: {cliente.nome or '(não cadastrado)'}",
        f"email: {cliente.email or '(não cadastrado)'}",
        f"doc: {cliente.doc or '(não cadastrado)'}",
        f"status: {cliente.status}",
        f"tags: {', '.join(cliente.tags) if cliente.tags else '(sem tags)'}",
    ]
    return "\n".join(parts)


@tool
async def get_cliente_history(
    limit: int = 5,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Lista os últimos atendimentos do cliente (exclui o atual).

    Use pra entender se é cliente recorrente ou tem histórico recente.
    Argumento `limit` (max 10): quantidade de atendimentos retornados.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    limit = max(1, min(int(limit), 10))
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    historico = await list_atendimentos_by_cliente(
        pool,
        empresa_id,
        atd.cliente_id,
        limit=limit,
        exclude_id=atendimento_id,
    )
    if not historico:
        return "Cliente novo — não há atendimentos anteriores."
    lines = [
        f"- #{a.id} ({a.status}) em {a.created_at.date().isoformat()}, agente {a.agente_atual}"
        for a in historico
    ]
    return f"Últimos {len(historico)} atendimento(s):\n" + "\n".join(lines)


@tool
async def get_cliente_anotacoes(
    limit: int = 10,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Lê as anotações do cliente (notas internas dos operadores).

    Use pra capturar contexto histórico antes de responder. Anotações
    são privadas (cliente não vê) e podem conter informações sensíveis
    (ex: "cliente reclamão, paciência"). NÃO repita literalmente — use
    como contexto pra calibrar o tom.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    limit = max(1, min(int(limit), 30))
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    anotacoes = await list_anotacoes(pool, atd.cliente_id, limit=limit)
    if not anotacoes:
        return "Cliente sem anotações."
    lines = [
        f"- [{a.created_at.date().isoformat()} por {a.user_id}] {a.conteudo}"
        for a in anotacoes
    ]
    return f"{len(anotacoes)} anotação(ões):\n" + "\n".join(lines)


# --- Escrita ---


@tool
async def create_cliente_anotacao(
    conteudo: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Cria uma anotação privada sobre o cliente (até 1000 chars).

    Use pra registrar contexto importante que vale pra atendimentos
    futuros (ex: "cliente prefere comunicação por email", "tem
    restrição alimentar X"). Não use pra fatos óbvios; foque em coisas
    que NÃO estejam em uma das outras tools (perfil, tags, histórico).
    """
    conteudo = conteudo.strip()
    if not conteudo:
        return "Nada anotado — conteúdo vazio."
    if len(conteudo) > 1000:
        conteudo = conteudo[:1000]
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    user_id = _extract_user_id(runtime)
    anotacao = await add_anotacao(pool, atd.cliente_id, user_id, conteudo)
    logger.info(
        "agent_tool_anotacao_created",
        empresa_id=empresa_id,
        cliente_id=atd.cliente_id,
        anotacao_id=anotacao.id,
    )
    return f"Anotação registrada (#{anotacao.id})."


@tool
async def add_cliente_tag(
    tag: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Adiciona uma tag ao cliente — categorização rápida.

    Use pra classificar (ex: "vip", "lead-frio", "alergico-lactose",
    "cancelou"). Tags são listadas em `get_cliente_profile` e visíveis
    no painel /clientes. Limite ~30 chars; em snake_case ou kebab-case.
    """
    tag = tag.strip().lower()
    if not tag:
        return "Tag vazia ignorada."
    if len(tag) > 30:
        tag = tag[:30]
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    await add_tag(pool, atd.cliente_id, tag)
    logger.info(
        "agent_tool_tag_added",
        empresa_id=empresa_id,
        cliente_id=atd.cliente_id,
        tag=tag,
    )
    return f"Tag '{tag}' adicionada ao cliente."


@tool
async def update_cliente(
    nome: str | None = None,
    email: str | None = None,
    doc: str | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Atualiza dados básicos do cliente (nome, email, doc).

    Use SOMENTE quando o cliente DECLARAR explicitamente (ex: "meu nome
    é João", "meu CPF é 12345"). Não invente nem deduza. Passe apenas
    os campos novos — o resto fica intocado.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    nome = (nome or "").strip() or None
    email = (email or "").strip() or None
    doc = (doc or "").strip() or None
    if not any((nome, email, doc)):
        return "Nada pra atualizar."
    cliente = await update_cliente_partial(
        pool, empresa_id, atd.cliente_id, nome=nome, email=email, doc=doc
    )
    if cliente is None:
        return "Cliente não encontrado."
    logger.info(
        "agent_tool_cliente_updated",
        empresa_id=empresa_id,
        cliente_id=atd.cliente_id,
        fields={"nome": bool(nome), "email": bool(email), "doc": bool(doc)},
    )
    fields_set = [k for k, v in (("nome", nome), ("email", email), ("doc", doc)) if v]
    return f"Cliente atualizado ({', '.join(fields_set)})."


@tool
async def close_atendimento(
    motivo: str = "resolvido",
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Fecha o atendimento atual marcando como resolvido (ou abandonado).

    Use quando a conversa terminou — cliente confirmou que está tudo
    certo, ou pediu pra encerrar. `motivo` aceita "resolvido" (default)
    ou "abandonado". Depois de fechado, mensagens novas do cliente
    abrem um atendimento novo.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    motivo = motivo.strip().lower() or "resolvido"
    if motivo not in ("resolvido", "abandonado"):
        motivo = "resolvido"
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    if atd.status not in ("aguardando", "em_andamento"):
        return f"Atendimento já está em status '{atd.status}'."
    closed = await _close_atendimento(pool, atendimento_id, motivo)
    if closed is None:
        return "Não consegui fechar o atendimento."
    logger.info(
        "agent_tool_atendimento_closed",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        motivo=motivo,
    )
    return f"Atendimento #{atendimento_id} fechado como {motivo}."


@tool
async def transfer_to_human(
    motivo: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Sinaliza que o atendimento precisa de operador humano.

    NÃO transfere automaticamente — adiciona tag `handoff` no cliente +
    cria anotação `[HANDOFF SOLICITADO] {motivo}`. Operadores veem o
    atendimento na fila /atendimento (aguardando) e clicam pra atender.

    Use quando: (1) cliente pedir explicitamente atendimento humano;
    (2) tema fora de seu escopo (jurídico, ouvidoria); (3) reclamação
    delicada que exige empatia humana. Depois de chamar essa tool,
    avise o cliente que vai passar pra um atendente — não tente
    resolver sozinho.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    motivo = motivo.strip()[:500] or "sem motivo informado"
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    user_id = _extract_user_id(runtime)
    await add_tag(pool, atd.cliente_id, "handoff")
    await add_anotacao(
        pool,
        atd.cliente_id,
        user_id,
        f"[HANDOFF SOLICITADO] {motivo}",
    )
    logger.info(
        "agent_tool_handoff_requested",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        cliente_id=atd.cliente_id,
        motivo=motivo,
    )
    return (
        "Sinalizado pra atendimento humano. Avise o cliente que um "
        "atendente vai entrar em contato."
    )
