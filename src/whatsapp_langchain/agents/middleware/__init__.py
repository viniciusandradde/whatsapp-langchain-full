"""Middlewares reutilizáveis para agentes LangGraph.

Este módulo contém middlewares que podem ser usados por qualquer agente
do projeto para gerenciar contexto, validar entrada, etc.

Exemplo:
    from whatsapp_langchain.agents.middleware import get_context_middleware

    middlewares = get_context_middleware()
    agent = create_agent(model=model, middleware=middlewares, ...)
"""

from whatsapp_langchain.agents.middleware.context import get_context_middleware
from whatsapp_langchain.agents.middleware.summarize import create_summarize_middleware
from whatsapp_langchain.agents.middleware.trim import create_trim_middleware

__all__ = [
    "get_context_middleware",
    "create_trim_middleware",
    "create_summarize_middleware",
]
