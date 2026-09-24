"""Aviso de entrega da Cloud API → estado da mensagem (mig 203)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.integrations.waba.webhook import parse_statuses
from whatsapp_langchain.shared import entrega
from whatsapp_langchain.shared.entrega import (
    ClienteQueRegistraEnvio,
    aplicar_status,
    motivo_da_falha,
)


def _payload(*statuses: dict) -> dict:
    """Formato da Meta (webhook `messages`, `value.statuses[]`)."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "556799288039",
                                "phone_number_id": "1245381968647556",
                            },
                            "statuses": list(statuses),
                        },
                    }
                ],
            }
        ],
    }


FALHOU_24H = {
    "id": "wamid.FALHOU",
    "status": "failed",
    "timestamp": "1758740000",
    "recipient_id": "556784249725",
    "errors": [
        {
            "code": 131047,
            "title": "Re-engagement message",
            "message": "Re-engagement message",
            "error_data": {
                "details": "Message failed to send because more than 24 hours "
                "have passed since the customer last replied to this number."
            },
        }
    ],
}
ENTREGUE = {
    "id": "wamid.OK",
    "status": "delivered",
    "timestamp": "1758740001",
    "recipient_id": "556784249725",
    "conversation": {"id": "c1", "origin": {"type": "service"}},
    "pricing": {"billable": True, "category": "service"},
}


def test_parse_statuses_le_falha_e_entrega():
    out = parse_statuses(_payload(FALHOU_24H, ENTREGUE))
    assert [(s.message_id, s.status) for s in out] == [
        ("wamid.FALHOU", "failed"),
        ("wamid.OK", "delivered"),
    ]
    falha = out[0]
    assert falha.waba_phone_id == "1245381968647556"
    assert (falha.erro_codigo, falha.erro_titulo) == (131047, "Re-engagement message")
    assert "24 hours" in (falha.erro_detalhe or "")
    assert out[1].erro_codigo is None


def test_parse_statuses_ignora_estado_desconhecido_e_outros_campos():
    assert parse_statuses(_payload({"id": "wamid.X", "status": "deleted"})) == []
    assert parse_statuses({"object": "page", "entry": []}) == []


def test_motivo_da_falha_legivel_com_codigo():
    assert motivo_da_falha(131047, "Re-engagement message", None).startswith(
        "Passaram mais de 24 horas"
    )
    assert motivo_da_falha(131047, None, None).endswith("(código 131047)")
    # Código fora da lista: o título da Meta, ainda com o código
    assert motivo_da_falha(999999, "Algo novo", None) == "Algo novo (código 999999)"
    assert motivo_da_falha(None, None, None) == "Falha na entrega"


def _pool(fetchone=None):
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=fetchone)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


async def test_falha_sempre_grava_e_restringe_a_conexao():
    pool, conn = _pool(fetchone=(42,))
    linha = await aplicar_status(
        pool, conexao_id=7, wamid="wamid.F", status="failed", erro="x"
    )
    assert linha == 42
    sql, params = conn.execute.await_args.args
    assert "conexao_id = %s" in sql
    assert "<> 'failed'" not in sql  # falha não tem guarda de ordem
    assert params == ("failed", "x", 7, "wamid.F")


async def test_estado_so_avanca_e_nao_apaga_falha():
    pool, conn = _pool(fetchone=None)
    linha = await aplicar_status(
        pool, conexao_id=7, wamid="wamid.F", status="delivered"
    )
    assert linha is None
    sql, params = conn.execute.await_args.args
    assert "entrega_status <> 'failed'" in sql
    assert params == ("delivered", None, 7, "wamid.F", 2)


async def test_invólucro_registra_o_wamid_e_repassa_o_resto():
    cliente = MagicMock()
    cliente.send_message = AsyncMock(return_value="wamid.NOVO")
    cliente.send_typing = AsyncMock(return_value=True)
    cliente.delivery_mode = "mock"
    registrar = AsyncMock()
    with patch.object(entrega, "registrar_envio", registrar):
        env = ClienteQueRegistraEnvio(cliente, MagicMock(), 99)
        assert await env.send_message("+5567", "oi") == "wamid.NOVO"
        assert await env.send_typing("+5567", "wamid.IN") is True
    registrar.assert_awaited_once()
    assert registrar.await_args.args[1:] == (99, "wamid.NOVO")
    assert env.delivery_mode == "mock"
    # WABA não tem send_audio: o getattr do worker continua vendo None
    del cliente.send_audio
    assert getattr(env, "send_audio", None) is None


async def test_falha_ao_registrar_nao_derruba_o_envio():
    cliente = MagicMock()
    cliente.send_message = AsyncMock(return_value="wamid.NOVO")
    with patch.object(
        entrega, "registrar_envio", AsyncMock(side_effect=RuntimeError("db"))
    ):
        env = ClienteQueRegistraEnvio(cliente, MagicMock(), 99)
        assert await env.send_message("+5567", "oi") == "wamid.NOVO"


@pytest.mark.parametrize("status", ["sent", "delivered", "read"])
async def test_ordem_dos_estados(status):
    pool, conn = _pool()
    await aplicar_status(pool, conexao_id=1, wamid="w", status=status)
    assert (
        conn.execute.await_args.args[1][-1]
        == {"sent": 1, "delivered": 2, "read": 3}[status]
    )
