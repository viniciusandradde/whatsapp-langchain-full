"""Compilador: pega `definicao_json` declarativa → CompiledStateGraph.

PoC: single workflow, sem subgraphs (`wf:xxx` refs ficam pra MVP).

Schema de `definicao`:
    {
        "entry": "boas_vindas",      # node_id de partida
        "nodes": {
            "<node_id>": {
                "type": "send_messages" | "ask_text" | "ask_choice" | "end",
                ... spec específico ...
                "next": "<next_node_id>"  (não usado por ask_choice e end)
            }
        }
    }
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from whatsapp_langchain.workflows.nodes import NODE_FACTORIES
from whatsapp_langchain.workflows.state import WorkflowState


def compile_workflow(
    definicao: dict[str, Any],
    *,
    checkpointer: BaseCheckpointSaver,
):
    """Compila uma `definicao` JSON em um CompiledStateGraph com
    checkpointer Postgres pra suportar interrupt + resume.

    Args:
        definicao: dict com keys `entry` e `nodes`
        checkpointer: AsyncPostgresSaver (ou SqliteSaver pra tests)

    Returns:
        CompiledStateGraph pronto pra `.ainvoke(state, config=...)`.
    """
    entry = definicao["entry"]
    nodes = definicao["nodes"]

    if entry not in nodes:
        raise ValueError(f"entry '{entry}' não está em nodes")

    builder: StateGraph = StateGraph(WorkflowState)

    # Adiciona nodes
    for node_id, spec in nodes.items():
        node_type = spec.get("type")
        if node_type not in NODE_FACTORIES:
            raise ValueError(
                f"node '{node_id}' tem type '{node_type}' desconhecido. "
                f"Suportados: {list(NODE_FACTORIES)}"
            )
        # Injeta `__node_id__` no spec pra history tracking
        spec_with_id = {**spec, "__node_id__": node_id}
        factory = NODE_FACTORIES[node_type]
        builder.add_node(node_id, factory(spec_with_id))

    # Adiciona edges
    builder.add_edge(START, entry)
    for node_id, spec in nodes.items():
        node_type = spec.get("type")
        # ask_choice e end usam Command(goto=...) — sem static edge
        if node_type in ("ask_choice", "end"):
            continue
        nxt = spec.get("next")
        if nxt is None:
            continue
        if nxt == "__end__" or nxt == END:
            builder.add_edge(node_id, END)
        else:
            if nxt not in nodes:
                raise ValueError(
                    f"node '{node_id}' aponta pra next='{nxt}' que não existe"
                )
            builder.add_edge(node_id, nxt)

    return builder.compile(checkpointer=checkpointer)
