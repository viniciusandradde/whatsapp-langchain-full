"""Tests dos node types adicionados no MVP: send_media, send_link,
set_var, branch.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from whatsapp_langchain.workflows import WorkflowRunner


@pytest.mark.asyncio
async def test_send_media_emits_media_kind():
    """Node send_media coloca item kind=media no outbox com URL+content_type."""
    defin = {
        "entry": "start",
        "nodes": {
            "start": {
                "type": "send_media",
                "url": "https://example.com/guia.pdf",
                "content_type": "application/pdf",
                "caption": "Olá {{vars.nome}}, segue o guia.",
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=1, empresa_id=1, msg="oi")
    assert any(
        m.get("kind") == "media" and m["url"].endswith("guia.pdf") for m in out
    ), f"esperava item kind=media; got {out}"


@pytest.mark.asyncio
async def test_send_link_includes_url():
    """Node send_link envia texto + URL no mesmo conteúdo."""
    defin = {
        "entry": "start",
        "nodes": {
            "start": {
                "type": "send_link",
                "url": "https://hospital.com/agendar",
                "text": "Agende online:",
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=2, empresa_id=1, msg="oi")
    txt = " ".join(m.get("text", "") for m in out)
    assert "Agende online" in txt
    assert "https://hospital.com/agendar" in txt


@pytest.mark.asyncio
async def test_set_var_persists_in_state():
    """Node set_var grava em vars (mensagens subsequentes podem renderizar)."""
    defin = {
        "entry": "set",
        "nodes": {
            "set": {
                "type": "set_var",
                "save_as": "greeting",
                "value": "Bom dia",
                "next": "msg",
            },
            "msg": {
                "type": "send_messages",
                "messages": ["{{vars.greeting}}, tudo bem?"],
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=3, empresa_id=1, msg="oi")
    assert any("Bom dia, tudo bem?" in m["text"] for m in out)


@pytest.mark.asyncio
async def test_branch_when_match():
    """Node branch direciona pro `next` da primeira condição que match."""
    defin = {
        "entry": "set",
        "nodes": {
            "set": {
                "type": "set_var",
                "save_as": "tier",
                "value": "premium",
                "next": "decide",
            },
            "decide": {
                "type": "branch",
                "when": [
                    {"condition": "vars.tier == 'free'", "next": "free_msg"},
                    {"condition": "vars.tier == 'premium'", "next": "premium_msg"},
                ],
                "else": "fallback",
            },
            "free_msg": {
                "type": "send_messages",
                "messages": ["Você é FREE"],
                "next": "__end__",
            },
            "premium_msg": {
                "type": "send_messages",
                "messages": ["Você é PREMIUM"],
                "next": "__end__",
            },
            "fallback": {
                "type": "send_messages",
                "messages": ["fallback"],
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=4, empresa_id=1, msg="oi")
    texts = [m.get("text", "") for m in out]
    assert any("PREMIUM" in t for t in texts), f"esperava ramo premium; got {texts}"


@pytest.mark.asyncio
async def test_branch_falls_to_else():
    """Nenhuma condição match → else."""
    defin = {
        "entry": "set",
        "nodes": {
            "set": {
                "type": "set_var",
                "save_as": "tier",
                "value": "enterprise",
                "next": "decide",
            },
            "decide": {
                "type": "branch",
                "when": [
                    {"condition": "vars.tier == 'free'", "next": "free_msg"},
                    {"condition": "vars.tier == 'premium'", "next": "premium_msg"},
                ],
                "else": "fallback",
            },
            "free_msg": {
                "type": "send_messages",
                "messages": ["Free"],
                "next": "__end__",
            },
            "premium_msg": {
                "type": "send_messages",
                "messages": ["Premium"],
                "next": "__end__",
            },
            "fallback": {
                "type": "send_messages",
                "messages": ["Outro plano"],
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=5, empresa_id=1, msg="oi")
    texts = [m.get("text", "") for m in out]
    assert any("Outro plano" in t for t in texts), f"esperava fallback; got {texts}"


@pytest.mark.asyncio
async def test_ask_text_with_cpf_validator():
    """ask_text com validate_with='cpf' rejeita CPF inválido."""
    defin = {
        "entry": "ask",
        "nodes": {
            "ask": {
                "type": "ask_text",
                "prompt": "Digite seu CPF:",
                "save_as": "cpf",
                "validate_with": "cpf",
                "next": "ok",
            },
            "ok": {
                "type": "send_messages",
                "messages": ["CPF aceito: {{vars.cpf}}"],
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    # turn 1: chega no ask
    out1 = await runner.process(atendimento_id=6, empresa_id=1, msg="oi")
    assert any("CPF" in m.get("text", "") for m in out1)

    # turn 2: envia CPF inválido — espera retry
    out2 = await runner.process(atendimento_id=6, empresa_id=1, msg="123")
    txt = " ".join(m.get("text", "") for m in out2)
    assert "inválido" in txt.lower() or "11 dígitos" in txt

    # turn 3: envia CPF válido — avança
    out3 = await runner.process(atendimento_id=6, empresa_id=1, msg="11144477735")
    txt = " ".join(m.get("text", "") for m in out3)
    assert "CPF aceito" in txt, f"esperava confirmação; got {txt}"
