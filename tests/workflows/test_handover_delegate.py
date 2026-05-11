"""Tests pros nodes que tocam atendimento (sem DB real — pool=None vira no-op).

MVP-B.1:
- transfer_departamento → message rendering OK mesmo sem pool
- handover → message rendering OK; vars sync skipped sem pool
- delegate_to_agent → message OK; UPDATE skipped sem pool
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from whatsapp_langchain.workflows import WorkflowRunner


@pytest.mark.asyncio
async def test_transfer_departamento_renders_message():
    defin = {
        "entry": "set",
        "nodes": {
            "set": {
                "type": "set_var",
                "save_as": "nome_cliente",
                "value": "Maria",
                "next": "transfer",
            },
            "transfer": {
                "type": "transfer_departamento",
                "departamento_id": 42,
                "message": (
                    "{{vars.nome_cliente}}, vou te transferir para Agendamentos. "
                    "Em breve um atendente irá te atender."
                ),
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())  # pool=None
    out = await runner.process(atendimento_id=1, empresa_id=1, msg="oi")
    texts = [m.get("text", "") for m in out]
    assert any("Maria" in t and "Agendamentos" in t for t in texts), (
        f"esperava msg personalizada; got {texts}"
    )


@pytest.mark.asyncio
async def test_handover_message_only_without_pool():
    """Sem pool, handover só envia message_to_client (sync DB é skipado)."""
    defin = {
        "entry": "set",
        "nodes": {
            "set": {
                "type": "set_var",
                "save_as": "nome_cliente",
                "value": "João",
                "next": "handover",
            },
            "handover": {
                "type": "handover",
                "resumo_template": "Cliente: {{vars.nome_cliente}}",
                "message_to_client": (
                    "Aguarde um momento, {{vars.nome_cliente}}, você está na fila."
                ),
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=2, empresa_id=1, msg="oi")
    texts = [m.get("text", "") for m in out]
    assert any("João" in t and "fila" in t for t in texts)


@pytest.mark.asyncio
async def test_delegate_to_agent_sends_optional_message():
    defin = {
        "entry": "delegate",
        "nodes": {
            "delegate": {
                "type": "delegate_to_agent",
                "agent_slug": "ouvidoria_avancada",
                "message": "Conectando você com nosso especialista...",
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    out = await runner.process(atendimento_id=3, empresa_id=1, msg="oi")
    texts = [m.get("text", "") for m in out]
    assert any("especialista" in t.lower() for t in texts), (
        f"esperava mensagem de delegação; got {texts}"
    )


@pytest.mark.asyncio
async def test_mackenzie_principal_flow_via_handover():
    """E2E approximado do menu_principal Mackenzie (versão simplificada com
    handover stub direto após menu_global → sem chamar sub-workflow real).
    """
    defin = {
        "entry": "boas",
        "nodes": {
            "boas": {
                "type": "send_messages",
                "messages": [
                    "Olá! Hospital Mackenzie.",
                    "Sou assistente virtual.",
                ],
                "next": "lgpd",
            },
            "lgpd": {
                "type": "ask_choice",
                "prompt": "Concorda com LGPD?",
                "choices": [
                    {"label": "Sim", "value": "1", "next": "ask_nome"},
                    {"label": "Não", "value": "2", "next": "encerrar"},
                ],
            },
            "ask_nome": {
                "type": "ask_text",
                "prompt": "Seu nome:",
                "save_as": "nome_cliente",
                "validate_with": "min_len:2",
                "next": "menu",
            },
            "menu": {
                "type": "ask_choice",
                "prompt": "Setor:",
                "choices": [
                    {"label": "Agendamentos", "value": "1", "next": "agend"},
                ],
            },
            "agend": {
                "type": "handover",
                "resumo_template": (
                    "Cliente: {{vars.nome_cliente}} | Setor: Agendamentos"
                ),
                "message_to_client": (
                    "Você está na fila, {{vars.nome_cliente}}."
                    " Aguarde um atendente."
                ),
                "next": "__end__",
            },
            "encerrar": {
                "type": "send_messages",
                "messages": ["Sem o aceite, não podemos prosseguir."],
                "next": "__end__",
            },
        },
    }
    runner = WorkflowRunner(defin, checkpointer=MemorySaver())
    # Turn 1
    out = await runner.process(atendimento_id=10, empresa_id=1, msg="oi")
    assert any("LGPD" in m["text"] or "Concorda" in m["text"] for m in out)
    # Turn 2: aceita LGPD
    out = await runner.process(atendimento_id=10, empresa_id=1, msg="1")
    assert any("nome" in m["text"].lower() for m in out)
    # Turn 3: nome
    out = await runner.process(atendimento_id=10, empresa_id=1, msg="João")
    assert any("Setor" in m["text"] or "Agendamentos" in m["text"] for m in out)
    # Turn 4: escolhe Agendamentos
    out = await runner.process(atendimento_id=10, empresa_id=1, msg="1")
    texts = [m["text"] for m in out]
    assert any("João" in t and "fila" in t for t in texts), (
        f"esperava handover personalizado; got {texts}"
    )
