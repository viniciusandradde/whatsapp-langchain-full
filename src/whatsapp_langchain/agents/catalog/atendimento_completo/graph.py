"""Factory de grafo pra `langgraph dev` / Studio (atendimento_completo)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from whatsapp_langchain.agents.catalog.atendimento_completo.agent import build_graph

if TYPE_CHECKING:
    from langgraph_sdk.runtime import ServerRuntime


def graph(runtime: ServerRuntime):
    """Constrói o agente usando store provido pelo runtime do LangGraph."""
    return build_graph(store=runtime.store)
