"""Smoke test e2e: webhook simulado → worker → outbound Twilio REAL → mark_done.

Requer:
  - Stack Docker rodando (make up) com TWILIO_OUTBOUND_MODE=real
  - .env com credenciais Twilio reais (ACCOUNT_SID, API_KEY_SID/SECRET, FROM_NUMBER)
  - TWILIO_LIVE_TESTS=1 e TWILIO_TEST_TO_NUMBER='+5511...' (E.164, número privado)
  - OPENROUTER_API_KEY válido (worker invoca o agente)

Custos: cada execução envia 1 mensagem WhatsApp real (~USD 0.005-0.05).

Uso:
    make up  # com .env preparado
    TWILIO_LIVE_TESTS=1 TWILIO_TEST_TO_NUMBER="+5511999999999" make test-twilio-smoke
"""
import os

import pytest

from .helpers import (
    assert_outbound_sent,
    send_webhook,
    unique_sid,
    wait_terminal_status,
)

pytestmark = pytest.mark.twilio_real


@pytest.fixture
def db_url():
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/whatsapp_langchain",
    )


def test_inbound_to_outbound_real_cycle(db_url, twilio_live_to_number):
    """Ciclo completo com Twilio real:

    1. Webhook simulado entra (igual aos outros docker_demo)
    2. Worker pega da fila, processa com agente real
    3. Worker envia outbound REAL via Twilio Messages API
    4. mark_done corre só após o envio retornar OK
    5. Asserções: status=done, response não-vazio, sem erro
    """
    sid = unique_sid("SMTWS")
    phone = twilio_live_to_number

    resp = send_webhook(
        phone=phone,
        body="Smoke test e2e — ignore. Responda apenas 'ok'.",
        message_sid=sid,
        agent="rhawk_assistant",
    )
    assert resp.status_code == 200, resp.text

    # Outbound real + LLM real = janela maior
    status, output, error, _ = wait_terminal_status(
        db_url, sid, timeout_seconds=120
    )
    assert status == "done", f"Falhou: status={status} error={error}"
    assert output and output.strip(), "Resposta vazia"

    # Garante que a row não foi para retry/failed
    info = assert_outbound_sent(db_url, sid)
    assert info["attempts"] == 1, f"Outbound falhou e foi retryado: {info}"
