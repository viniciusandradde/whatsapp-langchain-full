"""Entry point pra LangGraph Studio (`uv run langgraph dev`).

Cria store em memória pra Studio rodar sem DB. Em prod o `loader.py`
chama `build_graph()` com checkpointer + store reais.
"""

from langgraph.store.memory import InMemoryStore

from .agent import build_graph

store = InMemoryStore()
graph = build_graph(store=store)
