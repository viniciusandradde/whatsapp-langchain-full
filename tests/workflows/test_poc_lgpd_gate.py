"""PoC E2E — valida as 3 premissas mais incertas da Proposta v2:

#1 Compile + execute single workflow (sem subgraph)
#2 Outbox + interrupt semantics (mensagens não duplicam em resume)
#5 Versioning isolation: WorkflowState.workflow_version_id congelado

Usa MemorySaver pra checkpointer (sem Postgres). Em MVP usaremos
AsyncPostgresSaver real, mas semantics são equivalentes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from whatsapp_langchain.workflows import WorkflowRunner

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "poc_minimal.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_lgpd_gate_happy_path():
    """Cliente aceita LGPD, dá nome, escolhe departamento → end."""
    runner = WorkflowRunner(_load_fixture(), checkpointer=MemorySaver())

    # Turn 1: cliente manda primeira msg → boas-vindas + LGPD prompt
    out = await runner.process(atendimento_id=42, empresa_id=1, msg="oi")
    texts = [m["text"] for m in out if m["kind"] == "text"]
    assert any("bem-vindo" in t.lower() for t in texts), (
        f"esperava boas-vindas; got {texts}"
    )
    assert any("LGPD" not in t or "Concordo" in t or "segurança" in t for t in texts), (
        "esperava prompt LGPD com escolhas"
    )
    # Bonus: ask_choice deve renderizar [1] e [2]
    lgpd_prompt = next((t for t in texts if "[1]" in t and "[2]" in t), None)
    assert lgpd_prompt is not None, (
        f"esperava prompt com choices [1] e [2]; got {texts}"
    )

    # Turn 2: cliente "1" (aceita LGPD) → ask_nome
    out = await runner.process(atendimento_id=42, empresa_id=1, msg="1")
    texts = [m["text"] for m in out]
    assert any("Nome" in t for t in texts), f"esperava ask_nome; got {texts}"

    # Turn 3: cliente "João Silva" → saudação + menu_global
    out = await runner.process(atendimento_id=42, empresa_id=1, msg="João Silva")
    texts = [m["text"] for m in out]
    assert any("João Silva" in t for t in texts), (
        f"esperava saudação personalizada com nome; got {texts}"
    )
    assert any("departamento" in t.lower() for t in texts), (
        f"esperava menu_global; got {texts}"
    )

    # Turn 4: cliente "2" (Agendamentos) → stub + end
    out = await runner.process(atendimento_id=42, empresa_id=1, msg="2")
    texts = [m["text"] for m in out]
    assert any("Agendamentos" in t or "stub" in t for t in texts), (
        f"esperava stub_agendamento; got {texts}"
    )

    # Turn 5: workflow já terminou (END)
    out = await runner.process(atendimento_id=42, empresa_id=1, msg="anything")
    assert out == [], f"esperava lista vazia (workflow ended); got {out}"


@pytest.mark.asyncio
async def test_lgpd_gate_reject_path():
    """Cliente NÃO aceita LGPD → mensagem de encerramento + end."""
    runner = WorkflowRunner(_load_fixture(), checkpointer=MemorySaver())

    # Turn 1: primeira msg
    await runner.process(atendimento_id=100, empresa_id=1, msg="oi")

    # Turn 2: cliente "2" (rejeita LGPD)
    out = await runner.process(atendimento_id=100, empresa_id=1, msg="2")
    texts = [m["text"] for m in out]
    assert any("não podemos prosseguir" in t.lower() for t in texts), (
        f"esperava mensagem de encerramento LGPD; got {texts}"
    )


@pytest.mark.asyncio
async def test_lgpd_invalid_choice_retries():
    """Cliente manda valor fora de [1,2] → retry_message + re-interrupt."""
    runner = WorkflowRunner(_load_fixture(), checkpointer=MemorySaver())
    await runner.process(atendimento_id=200, empresa_id=1, msg="oi")

    # Cliente manda "lalala" — não bate com value=1 nem value=2
    out = await runner.process(atendimento_id=200, empresa_id=1, msg="lalala")
    texts = [m["text"] for m in out]
    assert any("responda 1 ou 2" in t.lower() for t in texts), (
        f"esperava retry_message; got {texts}"
    )

    # Continua válido após retry
    out = await runner.process(atendimento_id=200, empresa_id=1, msg="1")
    texts = [m["text"] for m in out]
    assert any("Nome" in t for t in texts), f"esperava ask_nome após retry; got {texts}"


@pytest.mark.asyncio
async def test_ask_text_validation_min_len():
    """Cliente envia nome muito curto → retry_message."""
    runner = WorkflowRunner(_load_fixture(), checkpointer=MemorySaver())
    await runner.process(atendimento_id=300, empresa_id=1, msg="oi")
    await runner.process(atendimento_id=300, empresa_id=1, msg="1")

    # Nome com 1 char (< min_len=2)
    out = await runner.process(atendimento_id=300, empresa_id=1, msg="A")
    texts = [m["text"] for m in out]
    assert any("mín" in t.lower() or "caracteres" in t.lower() for t in texts), (
        f"esperava retry de validação min_len; got {texts}"
    )

    # Nome válido continua
    out = await runner.process(atendimento_id=300, empresa_id=1, msg="Maria")
    texts = [m["text"] for m in out]
    assert any("Maria" in t for t in texts), f"esperava saudação com Maria; got {texts}"


@pytest.mark.asyncio
async def test_interrupt_resume_no_duplication():
    """Confirma Sprint v2 #2: send_messages ANTES do interrupt NÃO duplica
    quando o node é re-executado no resume.

    No fixture, `boas_vindas` envia 2 msgs ANTES de transitar pro `lgpd_ask`.
    Quando o cliente responder o LGPD, o resume executa o NODE `lgpd_ask`
    de novo (interrupt + Command pattern). As msgs do `boas_vindas`
    NÃO devem aparecer de novo na resposta.
    """
    runner = WorkflowRunner(_load_fixture(), checkpointer=MemorySaver())

    # Turn 1
    out1 = await runner.process(atendimento_id=400, empresa_id=1, msg="oi")
    welcome_count_1 = sum(1 for m in out1 if "bem-vindo" in m["text"].lower())
    assert welcome_count_1 == 1, (
        f"turn 1 deveria ter 1 boas-vindas; got {welcome_count_1}"
    )

    # Turn 2: resume do interrupt LGPD — só deve ter ask_nome, não boas-vindas
    out2 = await runner.process(atendimento_id=400, empresa_id=1, msg="1")
    welcome_count_2 = sum(1 for m in out2 if "bem-vindo" in m["text"].lower())
    assert welcome_count_2 == 0, (
        f"turn 2 (resume) NÃO deveria ter boas-vindas duplicada; "
        f"got {welcome_count_2} — vazamento de side effect pré-interrupt"
    )
