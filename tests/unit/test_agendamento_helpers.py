"""Tests dos helpers `shared/agendamento` (S2 Calendar v2).

Mocka pool/cursor pra evitar dep de DB real. Foca em:
- Validação de status válido
- Construção do row em Agendamento
- Filtros opcionais (status, cliente_id) montam SQL correto
- update_external_event passa params certos
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared import agendamento as ag


@pytest.fixture
def mock_pool_with_row():
    """Pool mock que retorna 1 row pra fetchone() e commit OK."""
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone = AsyncMock(
        return_value=(
            42,                                    # id
            1,                                     # empresa_id
            "primary",                             # calendar_id
            "user-uuid",                           # user_id_criador
            None,                                  # cliente_id
            "google-evt-id",                       # evento_id_externo
            "Reunião Wareline",                    # summary
            "descrição",                           # descricao
            datetime(2026, 5, 5, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 5, 15, 0, tzinfo=timezone.utc),
            "confirmado",                          # status
            True,                                  # aprovado
            False,                                 # gestor_notificado
            {"htmlLink": "https://..."},           # payload_externo
            datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),  # created_at
            datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),  # updated_at
        )
    )
    cur.fetchall = AsyncMock(return_value=[])
    cur.rowcount = 1
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn, cur


async def test_create_inserts_and_returns_object(mock_pool_with_row):
    pool, conn, cur = mock_pool_with_row
    out = await ag.create(
        pool,
        empresa_id=1,
        calendar_id="primary",
        summary="Reunião Wareline",
        data_inicio=datetime(2026, 5, 5, 14, 0, tzinfo=timezone.utc),
        data_fim=datetime(2026, 5, 5, 15, 0, tzinfo=timezone.utc),
        user_id_criador="user-uuid",
    )
    assert out.id == 42
    assert out.summary == "Reunião Wareline"
    assert out.status == "confirmado"
    conn.execute.assert_called_once()
    conn.commit.assert_called_once()


async def test_create_rejects_invalid_status(mock_pool_with_row):
    pool, _, _ = mock_pool_with_row
    with pytest.raises(ValueError, match="status inválido"):
        await ag.create(
            pool,
            empresa_id=1,
            calendar_id="primary",
            summary="x",
            data_inicio=datetime.now(timezone.utc),
            data_fim=datetime.now(timezone.utc),
            status="banana",
        )


async def test_get_by_id_scopes_by_empresa(mock_pool_with_row):
    pool, conn, _ = mock_pool_with_row
    out = await ag.get_by_id(pool, 42, 1)
    assert out is not None
    assert out.id == 42
    # Garante que empresa_id está na query
    args = conn.execute.call_args
    sql = args[0][0]
    params = args[0][1]
    assert "empresa_id = %s" in sql
    assert 42 in params and 1 in params


async def test_list_by_period_with_filters_appends_clauses(mock_pool_with_row):
    pool, conn, _ = mock_pool_with_row
    await ag.list_by_period(
        pool,
        1,
        inicio=datetime(2026, 5, 1, tzinfo=timezone.utc),
        fim=datetime(2026, 5, 31, tzinfo=timezone.utc),
        status="confirmado",
        cliente_id=99,
        limit=50,
    )
    sql = conn.execute.call_args[0][0]
    assert "data_inicio >= %s" in sql
    assert "data_inicio <= %s" in sql
    assert "status = %s" in sql
    assert "cliente_id = %s" in sql


async def test_list_by_period_invalid_status(mock_pool_with_row):
    pool, _, _ = mock_pool_with_row
    with pytest.raises(ValueError, match="status inválido"):
        await ag.list_by_period(
            pool,
            1,
            inicio=datetime.now(timezone.utc),
            fim=datetime.now(timezone.utc),
            status="zzz",
        )


async def test_update_external_event_serializes_jsonb(mock_pool_with_row):
    pool, conn, _ = mock_pool_with_row
    await ag.update_external_event(
        pool,
        42,
        evento_id_externo="g-evt-id",
        payload_externo={"htmlLink": "https://x", "attendees": []},
    )
    sql = conn.execute.call_args[0][0]
    params = conn.execute.call_args[0][1]
    assert "evento_id_externo = %s" in sql
    assert "payload_externo = %s::jsonb" in sql
    # Payload virou JSON string
    assert isinstance(params[1], str)
    assert "htmlLink" in params[1]


async def test_cancel_local_calls_update_status(mock_pool_with_row):
    pool, conn, _ = mock_pool_with_row
    ok = await ag.cancel_local(pool, 42, 1)
    assert ok is True
    sql = conn.execute.call_args[0][0]
    assert "status = %s" in sql
    assert "cancelado" in conn.execute.call_args[0][1]
