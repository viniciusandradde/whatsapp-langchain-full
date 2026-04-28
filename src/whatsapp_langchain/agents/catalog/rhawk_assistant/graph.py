"""Factory de grafo para uso com `langgraph dev`.

O runtime do LangGraph injeta store/checkpointer automaticamente em dev e em
deploy. Por isso, o entrypoint expõe uma factory compatível com `ServerRuntime`
em vez de um `Pregel` já compilado com componentes customizados.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from whatsapp_langchain.agents.catalog.rhawk_assistant.agent import build_graph

if TYPE_CHECKING:
    from langgraph_sdk.runtime import ServerRuntime


def graph(runtime: ServerRuntime):
    """Constrói o agente usando a store provida pelo runtime do LangGraph."""
    return build_graph(store=runtime.store)
