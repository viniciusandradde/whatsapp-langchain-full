"""Router classifier — decide quais sub-agentes ativar em paralelo.

Roda um LLM curto com structured output (Pydantic) sobre o último input
do cliente. Retorna lista de domínios de `DOMINIOS_VALIDOS`. Lista vazia
significa que nenhum especialista é necessário (saudação/despedida).

Sai do nó como state update `{"domains_needed": [...]}`. O conditional
edge `route_dispatch` lê esse campo e gera N `Send`s — um por sub-agente.

Decisões fixadas (plano):
- Modelo barato (Gemini 2.5 Flash via OpenRouter por default — caímos em
  fallback do `create_chat_model` se variável não setada).
- Cap em 3 sub-agentes paralelos. Lista maior é truncada na ordem em que
  o LLM retornou (que é a ordem de prioridade aprendida pelo prompt).
- Resposta direta (sem especialistas) pra `[]` — o synthesizer responde
  saudação/conversa fiada usando só as messages.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send
from pydantic import BaseModel, Field

from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import ROUTER_PROMPT
from .state import DOMINIOS_VALIDOS, RouterState

logger = structlog.get_logger()

_MAX_PARALLEL_SUBAGENTS = 3


class RouterDecision(BaseModel):
    """Saída estruturada do classifier."""

    domains: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de domínios a ativar. Use apenas: midia, crm, calendar, "
            "conhecimento. Lista vazia se nenhum especialista é necessário."
        ),
    )


def _filter_valid(domains: list[str]) -> list[str]:
    """Remove domínios inválidos + duplicatas, mantendo ordem do LLM."""
    seen: set[str] = set()
    out: list[str] = []
    for d in domains:
        d_clean = (d or "").strip().lower()
        if d_clean in DOMINIOS_VALIDOS and d_clean not in seen:
            out.append(d_clean)
            seen.add(d_clean)
    return out[:_MAX_PARALLEL_SUBAGENTS]


def _last_human_text(state: RouterState) -> str:
    """Extrai o conteúdo do último HumanMessage no state.

    O conteúdo já vem com prefixos `[Conteúdo do documento]:` etc do
    pré-processamento do worker — o classifier vê isso e decide se precisa
    de mídia/CRM/calendar/conhecimento.
    """
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


async def classify_router(state: RouterState) -> dict[str, Any]:
    """Nó router: classifica intent do último input → preenche `domains_needed`.

    Usa structured output Pydantic. Em caso de falha do LLM (rate limit,
    parse error), default seguro = lista vazia (synthesizer responde direto).
    """
    user_text = _last_human_text(state)
    media_type = state.get("media_type")

    if not user_text and not media_type:
        # Sem input nem mídia — caso degenerado, synthesizer cuida
        logger.info("router_skip_empty_input")
        return {"domains_needed": []}

    has_media_hint = (
        " [ANEXO PRESENTE]"
        if media_type
        or "[Descrição de imagem]" in user_text
        or "[Transcrição de áudio]" in user_text
        or "[Conteúdo do documento" in user_text
        else ""
    )

    try:
        llm = create_chat_model(temperature=0.0)
        structured = llm.with_structured_output(RouterDecision)
        decision = await structured.ainvoke(
            [
                SystemMessage(content=ROUTER_PROMPT),
                HumanMessage(content=user_text + has_media_hint),
            ]
        )
        if not isinstance(decision, RouterDecision):
            logger.warning(
                "router_decision_unexpected_type", got=type(decision).__name__
            )
            return {"domains_needed": []}
        domains = _filter_valid(decision.domains)
        logger.info(
            "router_decision",
            domains=domains,
            raw=decision.domains,
            has_media=bool(media_type),
        )
        return {"domains_needed": domains}
    except Exception as exc:
        logger.warning("router_classify_failed", error=str(exc))
        return {"domains_needed": []}


def route_dispatch(state: RouterState) -> list[Send] | str:
    """Conditional edge: gera 1 Send por domínio em paralelo.

    Se nenhum domínio foi escolhido, vai direto pro synthesizer (saudação,
    conversa fiada, ou fallback de erro do classifier).
    """
    domains = state.get("domains_needed") or []
    if not domains:
        return "synthesize"
    return [Send(f"agent_{domain}", state) for domain in domains]
