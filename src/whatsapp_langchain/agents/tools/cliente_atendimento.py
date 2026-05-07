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

from whatsapp_langchain.shared.agente import get_agente_by_slug
from whatsapp_langchain.shared.atendimento import (
    close_atendimento as _close_atendimento,
    complete_triagem,
    get_atendimento_by_id,
    list_atendimentos_by_cliente,
    set_classificacao,
)
from whatsapp_langchain.shared.cliente import (
    add_anotacao,
    add_tag,
    get_cliente_by_id,
    list_anotacoes,
    update_cliente_partial,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.departamento import get_departamento_by_id
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

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
async def classificar_atendimento(
    prioridade: str,
    sentimento: str,
    classificacao: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Registra classificação da triagem (silencioso — não menciona ao cliente).

    Chame ANTES de `transfer_to_human` pra que o atendente humano veja
    no drawer: badge prioridade, badge sentimento, chip classificação.
    Pode ser chamada múltiplas vezes — só a última prevalece.

    Args:
        prioridade: 'baixa' | 'media' | 'alta' | 'urgente'.
        sentimento: 'positivo' | 'neutro' | 'negativo' | 'frustrado'.
        classificacao: categoria curta em snake_case
            (ex: "suporte_login", "venda_consulta", "cobranca_negociacao").
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."
    try:
        result = await set_classificacao(
            pool,
            atendimento_id,
            prioridade=prioridade.strip().lower(),
            sentimento=sentimento.strip().lower(),
            classificacao=classificacao.strip().lower(),
        )
    except ValueError as exc:
        return f"Valor inválido: {exc}"
    if result is None:
        return "Não consegui classificar — atendimento não existe mais."
    logger.info(
        "agent_tool_classificar_atendimento",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        prioridade=result.prioridade,
        sentimento=result.sentimento,
        classificacao=result.classificacao,
    )
    return (
        f"Atendimento classificado: prioridade={result.prioridade}, "
        f"sentimento={result.sentimento}, categoria={result.classificacao}."
    )


@tool
async def transfer_to_human(
    motivo: str,
    resumo: str,
    prioridade: str | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Transfere o atendimento ao departamento humano configurado no agente.

    Departamento destino é DETERMINÍSTICO — fixado em
    `agente_ia.departamento_default_id` pelo admin no painel. Você NÃO
    escolhe departamento. Se o agente não tem depto configurado, retorna
    erro instrutivo (admin precisa setar primeiro).

    Antes de chamar essa tool, prefira `classificar_atendimento` pra
    registrar prioridade/sentimento/categoria (atendente vê tudo no drawer).

    Args:
        motivo: razão curta da transferência (ex: "Cliente pediu humano").
        resumo: resumo final pro atendente humano em 3-5 bullets curtos.
            Inclua: identificação do cliente, principal demanda, dados
            já coletados (CPF/protocolo se houver), próximos passos.
        prioridade: opcional — sobrescreve a prioridade já classificada.

    Sistema envia mensagem oficial ao cliente automaticamente após
    transferência. Você pode avisar em UMA frase ("vou passar pra equipe
    especializada"), mas não detalhe — sistema cuida do anúncio formal.
    """
    empresa_id, atendimento_id = _extract_ids(runtime)
    if empresa_id is None or atendimento_id is None:
        return "contexto incompleto."
    motivo_clean = motivo.strip()[:500] or "sem motivo informado"
    resumo_clean = (resumo or "").strip()
    if not resumo_clean:
        return (
            "ERRO: o resumo é obrigatório. Forneça 3-5 bullets curtos "
            "descrevendo cliente, demanda, dados coletados, próximos passos."
        )
    resumo_clean = resumo_clean[:4000]

    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return "atendimento não encontrado."

    # Resolve agente atual via runtime config; fallback agente_atual do atendimento
    cfg = _extract_runtime_config(runtime)
    agente_slug = cfg.get("agent_id") or atd.agente_atual
    if not agente_slug:
        return "ERRO: não foi possível identificar o agente atual."

    agente = await get_agente_by_slug(pool, empresa_id, str(agente_slug))
    if agente is None or agente.departamento_default_id is None:
        return (
            f"ERRO: agente '{agente_slug}' sem departamento configurado. "
            f"Peça ao admin pra setar 'Departamento padrão' em "
            f"/agents/db/{agente_slug}/edit antes de tentar transferir."
        )

    dep = await get_departamento_by_id(pool, empresa_id, agente.departamento_default_id)
    if dep is None or not dep.ativo:
        return (
            f"ERRO: departamento configurado (#{agente.departamento_default_id}) "
            f"não existe ou está inativo. Avise o admin."
        )

    # 1. UPDATE atendimento (departamento + resumo + triagem_completa)
    atd_updated = await complete_triagem(
        pool,
        atendimento_id,
        departamento_id=dep.id,
        resumo_ia=resumo_clean,
        prioridade=prioridade.strip().lower() if prioridade else None,
    )
    if atd_updated is None:
        return "Não consegui transferir — atendimento não existe mais."

    # 2. Auditoria em atendimento_transferencia
    user_id = _extract_user_id(runtime)
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO atendimento_transferencia (
                atendimento_id, empresa_id,
                de_agente_slug, para_departamento_id,
                motivo, iniciado_por_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (atendimento_id, empresa_id, agente_slug, dep.id, motivo_clean, user_id),
        )
        await conn.commit()

    # 3. Tag + anotação (compat com filtros existentes que usam tag handoff)
    await add_tag(pool, atd.cliente_id, "handoff")
    await add_anotacao(
        pool,
        atd.cliente_id,
        user_id,
        f"[HANDOFF → {dep.nome}] {motivo_clean}\n\nResumo IA:\n{resumo_clean}",
    )

    # 4. Mensagem oficial ao cliente (Sprint B.1 — system outbound)
    try:
        from whatsapp_langchain.shared.outbound import send_system_outbound

        protocolo = atd_updated.protocolo or f"#{atendimento_id}"
        msg_oficial = (
            f"Seu atendimento foi transferido para o departamento de "
            f"*{dep.nome}*. Em breve um atendente dará continuidade. "
            f"Protocolo: {protocolo}."
        )
        await send_system_outbound(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            conteudo=msg_oficial,
        )
    except Exception as exc:
        # Não quebra a transferência se outbound falhar — só loga.
        logger.warning(
            "transfer_outbound_failed",
            atendimento_id=atendimento_id,
            error=str(exc),
        )

    # 5. Hook event payload rico (Sprint B.2)
    try:
        await dispatch_event(
            pool,
            empresa_id,
            "atendimento.transferido",
            {
                "atendimento_id": atendimento_id,
                "from_user_id": None,
                "to_user_id": None,
                "departamento_id": dep.id,
                "departamento_nome": dep.nome,
                "prioridade": atd_updated.prioridade,
                "classificacao": atd_updated.classificacao,
                "sentimento": atd_updated.sentimento,
                "resumo_ia": resumo_clean,
                "cliente_id": atd_updated.cliente_id,
                "cliente_nome": atd_updated.cliente_nome,
                "phone": atd_updated.cliente_telefone,
                "protocolo": atd_updated.protocolo,
                "motivo": motivo_clean,
                "iniciado_por": "agente",
                "agente_slug": agente_slug,
            },
        )
    except Exception as exc:
        logger.warning("transfer_hook_failed", error=str(exc))

    logger.info(
        "agent_tool_transfer_to_human",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        cliente_id=atd.cliente_id,
        departamento_id=dep.id,
        departamento_nome=dep.nome,
        agente_slug=agente_slug,
        motivo=motivo_clean,
        resumo_chars=len(resumo_clean),
    )
    return (
        f"Atendimento transferido para {dep.nome}. Cliente notificado "
        f"automaticamente. Aguarde o atendente humano assumir."
    )
