"""Sub-agentes especialistas — chamados em paralelo via Send.

Cada sub-agente é um node assíncrono que:
1. Recebe o `RouterState` (já tem messages + media_url + domains_needed).
2. Constrói um `create_agent` stateless com toolset restrito ao domínio.
3. Invoca o agente passando só o último HumanMessage (sem checkpointer).
4. Retorna `{"domain_outputs": {dominio: texto}}` — reducer dict-merge faz o fan-in.

Decisões fixadas (plano):
- Stateless: NÃO usam checkpointer (cada turno é one-shot dentro do
  sub-agente). O checkpointer global cuida do histórico no nível do graph.
- Toolset isolado: cada sub-agente vê APENAS suas tools.
- Falha graceful: exception vira string `[ERRO ...]` no domain_outputs —
  synthesizer interpreta como "especialista falhou" e segue.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig

from whatsapp_langchain.agents.tools import (
    add_cliente_tag,
    analyze_image,
    calendar_cancel_event,
    calendar_create_event,
    calendar_find_free_slots,
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_list_events,
    calendar_reschedule_event,
    calendar_set_active_calendar,
    close_atendimento,
    create_cliente_anotacao,
    extract_document,
    get_cliente_anotacoes,
    get_cliente_history,
    get_cliente_profile,
    read_cliente_memoria,
    read_memory,
    save_cliente_fato,
    save_memory,
    search_knowledge_base,
    summarize_document,
    transcribe_audio,
    transfer_to_human,
    update_cliente,
)
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import (
    AGENT_CALENDAR_PROMPT,
    AGENT_CONHECIMENTO_PROMPT,
    AGENT_CRM_PROMPT,
    AGENT_MIDIA_PROMPT,
)
from .state import RouterState

logger = structlog.get_logger()

# Toolsets fixos por domínio
_TOOLS_MIDIA = [analyze_image, transcribe_audio, extract_document, summarize_document]
_TOOLS_CRM = [
    get_cliente_profile,
    get_cliente_history,
    get_cliente_anotacoes,
    create_cliente_anotacao,
    add_cliente_tag,
    update_cliente,
    close_atendimento,
    transfer_to_human,
]
_TOOLS_CALENDAR = [
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_set_active_calendar,
    calendar_list_events,
    calendar_find_free_slots,
    calendar_create_event,
    calendar_reschedule_event,
    calendar_cancel_event,
]
_TOOLS_CONHECIMENTO = [
    search_knowledge_base,
    save_memory,
    read_memory,
    save_cliente_fato,
    read_cliente_memoria,
]


def _last_human(state: RouterState) -> HumanMessage | None:
    """Pega o último HumanMessage do state (entrada do sub-agente)."""
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def _extract_text(message: Any) -> str:
    """Concatena partes textuais de um AIMessage."""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts).strip()
    return ""


async def _run_sub_agent(
    domain: str,
    system_prompt: str,
    tools: list,
    state: RouterState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Executor genérico — fabrica e invoca um sub-agente stateless."""
    last = _last_human(state)
    if last is None:
        logger.warning("sub_agent_no_input", domain=domain)
        return {"domain_outputs": {domain: "[ERRO: input ausente]"}}

    try:
        # Sub-agente stateless: sem checkpointer/store. Tools que precisam de
        # contexto de memória/cliente leem direto do RunnableConfig (já vem
        # populado pelo worker no nível do graph).
        agent = create_agent(
            model=create_chat_model(),
            tools=tools,
            system_prompt=system_prompt,
        )
        result = await agent.ainvoke({"messages": [last]}, config=config)
        # `result["messages"]` contém o histórico completo da execução do sub-agente.
        # Pegamos a última AIMessage (resposta final do sub-agente).
        out_messages = result.get("messages", []) if isinstance(result, dict) else []
        final_text = ""
        for msg in reversed(out_messages):
            if isinstance(msg, AIMessage):
                text = _extract_text(msg)
                if text:
                    final_text = text
                    break
        if not final_text:
            final_text = "[Sem resposta do especialista.]"
        logger.info(
            "sub_agent_invoked",
            domain=domain,
            steps=len(out_messages),
            output_chars=len(final_text),
        )
        return {"domain_outputs": {domain: final_text}}
    except Exception as exc:
        logger.warning("sub_agent_failed", domain=domain, error=str(exc))
        return {
            "domain_outputs": {domain: f"[ERRO no especialista {domain}: {exc!s:.200}]"}
        }


async def agent_midia_node(
    state: RouterState, config: RunnableConfig
) -> dict[str, Any]:
    return await _run_sub_agent(
        "midia", AGENT_MIDIA_PROMPT, _TOOLS_MIDIA, state, config
    )


async def agent_crm_node(state: RouterState, config: RunnableConfig) -> dict[str, Any]:
    return await _run_sub_agent("crm", AGENT_CRM_PROMPT, _TOOLS_CRM, state, config)


async def agent_calendar_node(
    state: RouterState, config: RunnableConfig
) -> dict[str, Any]:
    return await _run_sub_agent(
        "calendar", AGENT_CALENDAR_PROMPT, _TOOLS_CALENDAR, state, config
    )


async def agent_conhecimento_node(
    state: RouterState, config: RunnableConfig
) -> dict[str, Any]:
    return await _run_sub_agent(
        "conhecimento", AGENT_CONHECIMENTO_PROMPT, _TOOLS_CONHECIMENTO, state, config
    )


SUB_AGENT_NODES = {
    "agent_midia": agent_midia_node,
    "agent_crm": agent_crm_node,
    "agent_calendar": agent_calendar_node,
    "agent_conhecimento": agent_conhecimento_node,
}
