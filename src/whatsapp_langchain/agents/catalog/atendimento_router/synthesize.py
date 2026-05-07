"""Synthesizer — agrega outputs dos sub-agentes paralelos em resposta única.

Roda DEPOIS do fan-in dos sub-agentes (ou direto após router quando
nenhum especialista foi acionado). Usa o `SYNTHESIZE_PROMPT` (mesmo
modelo principal configurado no agente) pra gerar resposta pt-BR coerente.

Casos:
1. `domain_outputs` vazio → cliente está só conversando (saudação,
   despedida, "obrigado"). Synthesizer responde direto baseado no histórico.
2. `domain_outputs` com 1 entry → ajusta tom e devolve.
3. `domain_outputs` com múltiplos entries → integra narrativa.

Saída: `{"messages": [AIMessage(...)]}` — junta no histórico via add_messages.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from whatsapp_langchain.shared.llm import create_chat_model

from .state import RouterState

logger = structlog.get_logger()

_DOMAIN_LABEL = {
    "midia": "Especialista em Mídia",
    "crm": "Especialista em CRM/Atendimento",
    "calendar": "Especialista em Calendário",
    "conhecimento": "Especialista em Base de Conhecimento",
}


def _format_domain_outputs(outputs: dict[str, str]) -> str:
    if not outputs:
        return "(nenhum especialista foi acionado nesse turno)"
    lines: list[str] = []
    for domain, text in outputs.items():
        label = _DOMAIN_LABEL.get(domain, domain)
        lines.append(f"### {label}\n{text.strip()}")
    return "\n\n".join(lines)


def _last_human_text(state: RouterState) -> str:
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(str(part["text"]))
                    elif isinstance(part, str):
                        parts.append(part)
                return "\n".join(parts)
    return ""


def make_synthesize_node(system_prompt: str):
    """Fábrica do node synthesize com o SYSTEM_PROMPT já renderizado.

    Recebe `system_prompt` pra que o `loader.py` possa aplicar
    `prompt_override` antes da compilação do graph.
    """

    async def synthesize_node(
        state: RouterState, config: RunnableConfig
    ) -> dict[str, Any]:
        outputs = state.get("domain_outputs") or {}
        user_text = _last_human_text(state)
        domains_needed = state.get("domains_needed") or []

        synth_input = (
            "INPUT DO CLIENTE:\n"
            f"{user_text or '(input vazio)'}\n\n"
            "OUTPUTS DOS ESPECIALISTAS (em paralelo):\n"
            f"{_format_domain_outputs(outputs)}\n\n"
            "Sua tarefa: produza UMA resposta única ao cliente, em pt-BR, "
            "respeitando as regras do system prompt."
        )

        try:
            llm = create_chat_model()
            messages: list[BaseMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=synth_input),
            ]
            resp = await llm.ainvoke(messages, config=config)
            text = resp.content if isinstance(resp.content, str) else ""
            if not text and isinstance(resp.content, list):
                # Provedor pode devolver lista de partes — concatena texto
                parts: list[str] = []
                for part in resp.content:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(str(part["text"]))
                    elif isinstance(part, str):
                        parts.append(part)
                text = "\n".join(parts)
            text = text.strip() or (
                "Desculpe, não consegui processar agora. Pode reformular?"
            )
            logger.info(
                "synthesize_done",
                domains=domains_needed,
                outputs_count=len(outputs),
                response_chars=len(text),
            )
            return {"messages": [AIMessage(content=text)], "synthesized_response": text}
        except Exception as exc:
            logger.warning("synthesize_failed", error=str(exc))
            fallback = "Tive um problema ao gerar sua resposta. Pode reenviar?"
            return {
                "messages": [AIMessage(content=fallback)],
                "synthesized_response": fallback,
            }

    return synthesize_node
