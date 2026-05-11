"""Testes do compiler com sub-workflows (`wf:` refs) — MVP #1.

Cobre:
- compile_workflow_root resolve refs cross-workflow
- ciclo detectado é WARN (não erro)
- navegação root → sub → __end__ funciona
"""

from __future__ import annotations

import logging

import pytest
from langgraph.checkpoint.memory import MemorySaver

from whatsapp_langchain.workflows.compiler import (
    _detect_ref_cycle,
    compile_workflow_root,
)

ROOT_WF = {
    "entry": "saudacao",
    "nodes": {
        "saudacao": {
            "type": "send_messages",
            "messages": ["Bem-vindo!"],
            "next": "escolha",
        },
        "escolha": {
            "type": "ask_choice",
            "prompt": "Pra onde?",
            "choices": [
                {"label": "Sub A", "value": "1", "next": "wf:sub_a"},
                {"label": "Sub B", "value": "2", "next": "wf:sub_b"},
            ],
        },
    },
}

SUB_A_WF = {
    "entry": "msg_a",
    "nodes": {
        "msg_a": {
            "type": "send_messages",
            "messages": ["Você está no Sub A."],
            "next": "__end__",
        },
    },
}

SUB_B_WF = {
    "entry": "msg_b",
    "nodes": {
        "msg_b": {
            "type": "send_messages",
            "messages": ["Você está no Sub B."],
            "next": "__end__",
        },
    },
}


def test_compile_root_with_subgraphs():
    """Root + 2 subworkflows compilam sem erro."""
    definicoes = {"root": ROOT_WF, "sub_a": SUB_A_WF, "sub_b": SUB_B_WF}
    graph = compile_workflow_root("root", definicoes, checkpointer=MemorySaver())
    assert graph is not None


def test_cycle_detection_returns_path():
    """Ciclo entre 2 workflows é detectado."""
    a = {
        "entry": "n1",
        "nodes": {"n1": {"type": "send_messages", "messages": ["a"], "next": "wf:b"}},
    }
    b = {
        "entry": "n1",
        "nodes": {"n1": {"type": "send_messages", "messages": ["b"], "next": "wf:a"}},
    }
    cycle = _detect_ref_cycle(["a", "b"], {"a": a, "b": b})
    assert cycle is not None
    assert set(cycle) >= {"a", "b"}


def test_cycle_warns_not_fails(caplog):
    """Ciclo emite logger.warning mas não levanta exception."""
    a = {
        "entry": "n1",
        "nodes": {"n1": {"type": "send_messages", "messages": ["a"], "next": "wf:b"}},
    }
    b = {
        "entry": "n1",
        "nodes": {"n1": {"type": "send_messages", "messages": ["b"], "next": "wf:a"}},
    }
    with caplog.at_level(
        logging.WARNING, logger="whatsapp_langchain.workflows.compiler"
    ):
        graph = compile_workflow_root("a", {"a": a, "b": b}, checkpointer=MemorySaver())
    assert graph is not None
    assert any("cycle" in rec.message.lower() for rec in caplog.records), (
        f"esperava log de cycle; got {[r.message for r in caplog.records]}"
    )


def test_missing_subgraph_ref_fails():
    """Ref pra subgraph não fornecido → ValueError."""
    root = {
        "entry": "n1",
        "nodes": {
            "n1": {"type": "send_messages", "messages": ["a"], "next": "wf:missing"},
        },
    }
    with pytest.raises(ValueError, match="wf:missing"):
        compile_workflow_root("root", {"root": root}, checkpointer=MemorySaver())
