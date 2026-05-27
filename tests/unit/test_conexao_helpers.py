"""Testes dos helpers de conexão WhatsApp."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.conexao import (
    get_conexao_by_from_number,
    get_conexao_by_id,
    list_conexoes,
    set_conexao_status,
    upsert_conexao,
)
from whatsapp_langchain.shared.models import ConexaoInput


def _row(
    *,
    id_=1,
    empresa_id=1,
    provider="twilio_sandbox",
    sid="ACxxxx",
    from_number="+14155238886",
    display_name="Sandbox",
    default_agent_id="vsa_tech",
    status="active",
    is_default=True,
    payload_json=None,
    connection_state="pending",
    state_message=None,
):
    """Tupla mockada de SELECT (ordem bate com _SELECT_COLS em conexao.py)."""
    now = datetime.now(UTC)
    return (
        id_,
        empresa_id,
        provider,
        sid,
        from_number,
        display_name,
        default_agent_id,
        status,
        is_default,
        payload_json or {},
        now,
        now,
        "ia",            # tipo_atendimento
        None,            # whatsapp_state
        None,            # waba_account_id
        None,            # waba_phone_id
        None,            # waba_app_id
        None,            # waba_account_description
        connection_state,
        state_message,
        None,            # qr_code
        None,            # qr_expires_at
        None,            # ultimo_health_check_at
        None,            # ultimo_health_check_ok
        None,            # webhook_verify_token
    )


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    """Pool com fetchone/fetchall retornando results sequenciais.

    Quando o último item é list, ele vai pra fetchall; senão, pra fetchone.
    """
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_lookup_by_from_number_returns_conexao():
    pool, _ = _mock_pool(_row(from_number="+5511999999999"))
    c = await get_conexao_by_from_number(pool, "+5511999999999")
    assert c is not None
    assert c.from_number == "+5511999999999"


@pytest.mark.asyncio
async def test_lookup_by_from_number_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    c = await get_conexao_by_from_number(pool, "+5511000")
    assert c is None


@pytest.mark.asyncio
async def test_get_conexao_by_id_hits_pk():
    pool, _ = _mock_pool(_row(id_=42))
    c = await get_conexao_by_id(pool, 42)
    assert c is not None
    assert c.id == 42


@pytest.mark.asyncio
async def test_list_conexoes_filters_by_empresa():
    rows = [_row(id_=1, empresa_id=2), _row(id_=2, empresa_id=2, is_default=False)]
    pool, conn = _mock_pool(rows)
    result = await list_conexoes(pool, 2)
    assert len(result) == 2
    assert all(c.empresa_id == 2 for c in result)
    # SQL params devem conter o empresa_id
    args = conn.execute.await_args
    assert args.args[1] == (2,)


@pytest.mark.asyncio
async def test_upsert_conexao_returns_persisted_row():
    pool, conn = _mock_pool(
        _row(id_=10, provider="twilio_prod", from_number="+1555NEW")
    )
    data = ConexaoInput(
        provider="twilio_prod",
        from_number="+1555NEW",
        display_name="Linha prod",
        default_agent_id="vsa_tech",
    )
    out = await upsert_conexao(pool, 1, data)
    assert out.id == 10
    assert out.from_number == "+1555NEW"
    # INSERT executado (1ª execute do conn)
    first_sql = conn.execute.await_args_list[0].args[0]
    assert "INSERT INTO conexao" in first_sql
    assert "ON CONFLICT" in first_sql


@pytest.mark.asyncio
async def test_upsert_conexao_twilio_promotes_to_open():
    """Twilio (sandbox/prod) não tem callback de ativação como WABA/Evolution —
    `upsert_conexao` deve transicionar `connection_state` direto pra 'open'.
    Sem isso UI mostra "Pendente" indefinidamente."""
    pool, conn = _mock_pool(_row(id_=20, provider="twilio_sandbox"))
    data = ConexaoInput(
        provider="twilio_sandbox",
        from_number="+14155238886",
        display_name="Sandbox",
        default_agent_id="vsa_tech",
    )
    out = await upsert_conexao(pool, 1, data)
    assert out.connection_state == "open"
    assert out.state_message is not None and "Twilio" in out.state_message
    # 2 SQLs: INSERT + UPDATE connection_state (set_connection_state)
    sqls = [call.args[0] for call in conn.execute.await_args_list]
    assert any("INSERT INTO conexao" in s for s in sqls)
    assert any(
        "UPDATE conexao" in s and "connection_state" in s for s in sqls
    )


@pytest.mark.asyncio
async def test_upsert_conexao_waba_stays_pending():
    """WABA tem fluxo OAuth próprio — connection_state NÃO deve ser tocado
    pelo upsert (transição vira via /waba/finalize)."""
    pool, conn = _mock_pool(_row(id_=30, provider="waba", from_number="+5511WABA"))
    data = ConexaoInput(
        provider="waba",
        from_number="+5511WABA",
        display_name="WABA prod",
        default_agent_id="vsa_tech",
    )
    out = await upsert_conexao(pool, 1, data)
    assert out.connection_state == "pending"  # default da mig 092 preservado
    # Só 1 SQL: INSERT (nenhum UPDATE de connection_state)
    sqls = [call.args[0] for call in conn.execute.await_args_list]
    assert sum(1 for s in sqls if "INSERT INTO conexao" in s) == 1
    assert not any(
        "UPDATE conexao" in s and "connection_state" in s for s in sqls
    )


@pytest.mark.asyncio
async def test_set_conexao_status_runs_update():
    pool, conn = _mock_pool()
    await set_conexao_status(pool, 5, "disabled")
    sql = conn.execute.await_args.args[0]
    assert "UPDATE conexao SET status" in sql
    assert conn.execute.await_args.args[1] == ("disabled", 5)
