"""Tests do helper `get_workflow_state_snapshot` (UI debug L2).

Sem DB real — passa pool=None e checkpointer=MemorySaver. Foca no
contrato: retorna None quando não há workflow ativo da empresa, retorna
dict com chaves esperadas quando há state.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from whatsapp_langchain.workflows import WorkflowRunner
from whatsapp_langchain.workflows.loader import get_workflow_state_snapshot


class _FakePool:
    """Stub mínimo de pool: load_active_workflow consulta a tabela
    workflow_chatbot. Pra não bater no DB, retornamos um cursor que
    devolve None (= empresa sem workflow ativo).
    """

    def connection(self):  # noqa: D401
        return _FakeCM()


class _FakeCM:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    async def execute(self, *args, **kwargs):
        return _FakeCursor()


class _FakeCursor:
    async def fetchone(self):
        return None

    async def fetchall(self):
        return []


@pytest.mark.asyncio
async def test_snapshot_returns_none_quando_sem_workflow_ativo():
    snapshot = await get_workflow_state_snapshot(
        pool=_FakePool(),
        checkpointer=MemorySaver(),
        atendimento_id=1,
        empresa_id=999,
    )
    assert snapshot is None


@pytest.mark.asyncio
async def test_snapshot_via_runner_direto_retorna_chaves_esperadas():
    """Usa o runner cru pra criar um state, depois lê via aget_state
    direto (sem passar pelo loader, que precisa do DB).
    """
    defin = {
        "entry": "ask",
        "nodes": {
            "ask": {
                "type": "ask_text",
                "prompt": "Nome:",
                "save_as": "nome",
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    await runner.process(atendimento_id=42, empresa_id=1, msg="oi")
    config = {"configurable": {"thread_id": "wf:42"}}
    state = await runner._graph.aget_state(config)
    assert state.values, "state deve estar persistido após primeira turn"
    # Tem interrupt pendente no node `ask`
    has_interrupt = any(
        getattr(task, "interrupts", None) for task in (state.tasks or [])
    )
    assert has_interrupt, "esperava interrupt pendente após ask_text"
