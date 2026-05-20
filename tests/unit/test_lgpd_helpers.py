"""Tests dos helpers LGPD (log_event + verify_cliente_identity)."""

from datetime import UTC, date
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.lgpd import (
    EVENT_TYPES,
    LGPDEventTypeError,
    _normalize_cpf_ultimos4,
    _normalize_data,
    _normalize_nome,
    count_events,
    list_events,
    log_event,
    verify_cliente_identity,
)


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------- normalizers ----------


def test_normalize_nome_remove_acentos_e_caixa():
    assert _normalize_nome(" Maria Silva  ") == "maria silva"
    assert _normalize_nome("João da Silva") == "joao da silva"
    assert _normalize_nome("ANTÔNIO") == "antonio"


def test_normalize_data_aceita_varios_formatos():
    assert _normalize_data("15/03/1985") == date(1985, 3, 15)
    assert _normalize_data("1985-03-15") == date(1985, 3, 15)
    assert _normalize_data("15-03-1985") == date(1985, 3, 15)
    assert _normalize_data("invalido") is None
    assert _normalize_data("") is None


def test_normalize_cpf_extrai_4_ultimos_digitos():
    assert _normalize_cpf_ultimos4("123.456.789-00") == "8900"
    assert _normalize_cpf_ultimos4("12345678900") == "8900"
    assert _normalize_cpf_ultimos4("8900") == "8900"
    assert _normalize_cpf_ultimos4("89") is None
    assert _normalize_cpf_ultimos4("abc") is None


# ---------- log_event ----------


@pytest.mark.asyncio
async def test_log_event_grava_e_commita():
    pool, conn = _mock_pool((42,))
    event_id = await log_event(
        pool,
        empresa_id=1,
        event_type="cpf_collected",
        details={"motivo": "2via"},
        atendimento_id=10,
    )
    assert event_id == 42
    conn.execute.assert_called_once()
    conn.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_event_levanta_em_type_invalido():
    pool, _ = _mock_pool()
    with pytest.raises(LGPDEventTypeError):
        await log_event(
            pool, empresa_id=1, event_type="invento_qualquer"
        )


@pytest.mark.asyncio
async def test_log_event_aceita_todos_event_types_validos():
    for et in EVENT_TYPES:
        pool, _ = _mock_pool((1,))
        rid = await log_event(pool, empresa_id=1, event_type=et)
        assert rid == 1


# ---------- verify_cliente_identity ----------


@pytest.mark.asyncio
async def test_verify_match_exato():
    pool, _ = _mock_pool([(123, "Maria Silva", "12345678900")])
    r = await verify_cliente_identity(
        pool, 1, nome="Maria Silva", data_nascimento="15/03/1985", cpf_ultimos4="8900"
    )
    assert r == {"verified": True, "patient_id": 123}


@pytest.mark.asyncio
async def test_verify_match_com_acento_e_caixa():
    pool, _ = _mock_pool([(99, "João Pereira", "11122233344")])
    r = await verify_cliente_identity(
        pool, 1, nome="JOAO PEREIRA", data_nascimento="22/07/1972", cpf_ultimos4="3344"
    )
    assert r["verified"] is True
    assert r["patient_id"] == 99


@pytest.mark.asyncio
async def test_verify_nao_encontrado():
    pool, _ = _mock_pool([])
    r = await verify_cliente_identity(
        pool, 1, nome="Fulano", data_nascimento="01/01/2000", cpf_ultimos4="9999"
    )
    assert r == {"verified": False, "reason": "nao_encontrado"}


@pytest.mark.asyncio
async def test_verify_multiplos_matches():
    pool, _ = _mock_pool(
        [(1, "Maria Silva", "11111111111"), (2, "Maria Silva", "22222222222")]
    )
    r = await verify_cliente_identity(
        pool, 1, nome="Maria Silva", data_nascimento="15/03/1985", cpf_ultimos4="1111"
    )
    assert r == {"verified": False, "reason": "multiplos_matches"}


@pytest.mark.asyncio
async def test_verify_data_invalida():
    pool, _ = _mock_pool()
    r = await verify_cliente_identity(
        pool, 1, nome="x", data_nascimento="nao-e-data", cpf_ultimos4="1234"
    )
    assert r == {"verified": False, "reason": "data_invalida"}


@pytest.mark.asyncio
async def test_verify_cpf_curto():
    pool, _ = _mock_pool()
    r = await verify_cliente_identity(
        pool, 1, nome="x", data_nascimento="01/01/2000", cpf_ultimos4="12"
    )
    assert r == {"verified": False, "reason": "cpf_invalido"}


@pytest.mark.asyncio
async def test_verify_nome_vazio():
    pool, _ = _mock_pool()
    r = await verify_cliente_identity(
        pool, 1, nome="   ", data_nascimento="01/01/2000", cpf_ultimos4="9999"
    )
    assert r == {"verified": False, "reason": "nome_invalido"}


# ---------- list_events / count_events ----------


@pytest.mark.asyncio
async def test_list_events_aplica_filtros():
    from datetime import datetime

    now = datetime.now(UTC)
    pool, conn = _mock_pool(
        [
            (
                1, 5, 100, 50, "saude_atendimento_cliente", "u1",
                "cpf_collected", {"motivo": "2via"}, "1.2.3.4", now,
            )
        ]
    )
    out = await list_events(
        pool,
        5,
        event_type="cpf_collected",
        atendimento_id=100,
        limit=10,
    )
    assert len(out) == 1
    assert out[0]["event_type"] == "cpf_collected"
    assert out[0]["atendimento_id"] == 100
    # Confirma que SQL teve where com event_type + atendimento_id
    sql = conn.execute.await_args_list[0].args[0]
    assert "event_type = %s" in sql
    assert "atendimento_id = %s" in sql


@pytest.mark.asyncio
async def test_count_events_retorna_int():
    pool, _ = _mock_pool((42,))
    n = await count_events(pool, 1, event_type="cpf_collected")
    assert n == 42
