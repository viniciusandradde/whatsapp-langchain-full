"""WorkflowState — state TypedDict persistido via AsyncPostgresSaver.

Convenção:
- `vars` é dict acumulado via reducer (merge — não substitui)
- `outbox` é lista append-only (mensagens pra enviar ao cliente)
- `history` é lista append-only de node_ids visitados (debug)
- `workflow_version_id` (Sprint v2 — congelado por execução)
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


def _dict_merge(a: dict, b: dict) -> dict:
    """Reducer pra `vars`: merge shallow (b sobrescreve a)."""
    return {**a, **b}


class WorkflowState(TypedDict, total=False):
    """State persistido por thread_id no AsyncPostgresSaver.

    LangGraph aplica reducers Annotated[..., reducer_fn] em cada update.
    """

    atendimento_id: int
    empresa_id: int
    workflow_version_id: int  # versão congelada (Sprint v2 #5)
    vars: Annotated[dict[str, Any], _dict_merge]
    outbox: Annotated[list[dict[str, Any]], operator.add]  # mensagens a enviar
    history: Annotated[list[str], operator.add]  # node_ids visitados
    last_input: str | None
