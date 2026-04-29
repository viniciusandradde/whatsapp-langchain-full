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

import httpx
import psycopg
import pytest

from .helpers import (
    API_BASE_URL,
    assert_outbound_sent,
    get_db_url,
    send_webhook,
    unique_sid,
    wait_terminal_status,
)

pytestmark = pytest.mark.twilio_real


@pytest.fixture
def db_url() -> str:
    """Valida stack rodando e retorna URL do banco."""
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if response.status_code != 200:
            pytest.skip("API não saudável. Rode: make up com TWILIO_OUTBOUND_MODE=real")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique docker compose e DATABASE_URL")
    return url


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
        agent="vsa_tech",
    )
    assert resp.status_code == 200, resp.text

    # Outbound real + LLM real = janela maior
    status, output, error, _ = wait_terminal_status(db_url, sid, timeout_seconds=120)
    assert status == "done", f"Falhou: status={status} error={error}"
    assert output and output.strip(), "Resposta vazia"

    # Garante que a row não foi para retry/failed
    info = assert_outbound_sent(db_url, sid)
    assert info["attempts"] == 1, f"Outbound falhou e foi retryado: {info}"
