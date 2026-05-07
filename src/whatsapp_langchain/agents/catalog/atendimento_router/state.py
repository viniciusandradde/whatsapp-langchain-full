"""State schema do agente atendimento_router (Fase 2 multi-agent).

Padrão Router + Parallel Agents (LangChain docs):
- `messages`: histórico de chat (gerenciado pelo LangGraph)
- `media_url`/`media_type`: snapshot do anexo do turno (passa pra sub-agentes
  multimodais via runtime config)
- `domains_needed`: lista decidida pelo router classifier (ex: ["midia","crm"])
- `domain_outputs`: dict populado em paralelo via state reducer (operator.or_)
- `synthesized_response`: resposta final do synthesizer

Sub-agentes são stateless — recebem só `messages[-1]` + `media_url`.
Synthesizer agrega `domain_outputs` em resposta única pt-BR.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


def _merge_dict(left: dict | None, right: dict | None) -> dict:
    """Reducer pra domain_outputs — fan-in dos sub-agentes paralelos.

    Cada sub-agente roda em paralelo e atualiza domain_outputs com
    {dominio: texto}. LangGraph chama esse reducer pra mergear updates
    sem race condition.
    """
    if left is None:
        left = {}
    if right is None:
        right = {}
    return {**left, **right}


class RouterState(TypedDict, total=False):
    """State do StateGraph atendimento_router."""

    # Histórico (LangGraph gerencia via add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Anexo do turno (None quando texto puro). Worker injeta via configurable
    # também — duplicado aqui pra sub-agentes paralelos terem acesso fácil.
    media_url: str | None
    media_type: str | None

    # Decisão do router (classifier LLM)
    domains_needed: list[str]

    # Outputs dos sub-agentes paralelos (fan-in via reducer dict-merge)
    domain_outputs: Annotated[dict[str, str], _merge_dict]

    # Resposta final do synthesizer
    synthesized_response: str


# Domínios suportados — devem bater com keys em SUB_AGENT_FACTORIES (sub_agents.py)
DOMINIOS_VALIDOS = ("midia", "crm", "calendar", "conhecimento")
