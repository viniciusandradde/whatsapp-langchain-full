"""Agente Atendimento Router — multi-agent paralelo (Router + Parallel).

Topologia (LangChain docs / multi-agent / router#parallel):

    START → router (classifier) ─conditional Send─→ [agent_midia, agent_crm,
        agent_calendar, agent_conhecimento] (até 3 paralelos) → fan-in →
        synthesize → END

Mantém compatibilidade com a assinatura `build_graph()` que `loader.py`
chama (mesmo dos templates `vsa_tech` e `atendimento_completo`):
- recebe `checkpointer`, `store`, model overrides, flags `calendar_enabled`/
  `knowledge_enabled`, `system_prompt_override`.
- `calendar_enabled` / `knowledge_enabled` aqui são informativas: o router
  classifier sempre conhece os 4 domínios e sub-agentes lidam com indisponibilidade
  via tools (ex: search_knowledge_base devolve "sem KB" quando vazio).

Padrão de invocação (worker idêntico aos outros templates):
    graph = await load_graph(...)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(...)], "media_url": ..., "media_type": ...},
        config={"configurable": {"thread_id": ..., "user_id": ..., "media_url": ...}},
    )
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from .prompts import SYNTHESIZE_PROMPT
from .router import classify_router, route_dispatch
from .state import RouterState
from .sub_agents import SUB_AGENT_NODES
from .synthesize import make_synthesize_node


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,  # noqa: ARG001 — modelo lido via env (create_chat_model)
    pool: AsyncConnectionPool | None = None,  # noqa: ARG001
    empresa_id: int | None = None,  # noqa: ARG001
    calendar_enabled: bool = False,  # noqa: ARG001
    knowledge_enabled: bool = False,  # noqa: ARG001
    system_prompt_override: str | None = None,
    temperatura: float | None = None,  # noqa: ARG001
    top_p: float | None = None,  # noqa: ARG001
    max_tokens: int | None = None,  # noqa: ARG001
):
    """Compila o StateGraph multi-agent paralelo.

    `system_prompt_override` (se setado) substitui SYNTHESIZE_PROMPT — só
    o synthesizer respeita override. Sub-agentes têm prompts internos
    fixos (instruções operacionais, não tom do cliente).
    """
    effective_synth_prompt = (
        system_prompt_override
        if system_prompt_override and system_prompt_override.strip()
        else SYNTHESIZE_PROMPT
    )

    graph = StateGraph(RouterState)

    # Nodes
    graph.add_node("router", classify_router)
    for node_name, node_fn in SUB_AGENT_NODES.items():
        graph.add_node(node_name, node_fn)
    graph.add_node("synthesize", make_synthesize_node(effective_synth_prompt))

    # Edges
    graph.add_edge(START, "router")

    # Router → fan-out (Send) ou direto pro synthesize quando lista vazia
    graph.add_conditional_edges(
        "router",
        route_dispatch,
        # Path-map declara os destinos possíveis pra LangGraph validar.
        {
            "agent_midia": "agent_midia",
            "agent_crm": "agent_crm",
            "agent_calendar": "agent_calendar",
            "agent_conhecimento": "agent_conhecimento",
            "synthesize": "synthesize",
        },
    )

    # Fan-in: todo sub-agente pluga no synthesize.
    # Como sub-agentes rodam em paralelo via Send, o LangGraph aguarda todos
    # antes de avançar. Reducer dict-merge em domain_outputs evita race.
    for node_name in SUB_AGENT_NODES:
        graph.add_edge(node_name, "synthesize")

    graph.add_edge("synthesize", END)

    return graph.compile(checkpointer=checkpointer, store=store)
