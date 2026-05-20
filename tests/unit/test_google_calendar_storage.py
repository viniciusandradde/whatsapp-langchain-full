"""Tests do helper google_calendar_storage (dual-write + Fernet)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from whatsapp_langchain.integrations.crypto import encrypt_dict
from whatsapp_langchain.integrations.google_calendar_storage import (
    PROVIDER_SLUG,
    delete_dual,
    read_unified,
    refresh_credentials_dual,
    update_setting_dual,
    upsert_credentials_dual,
)


@pytest.fixture(autouse=True)
def _patch_fernet(monkeypatch):
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "wareline_encryption_key", SecretStr(key))


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


# ---------- read_unified ----------


@pytest.mark.asyncio
async def test_read_prefer_api_connection():
    """Quando api_connection tem row, usa ela (não fallback)."""
    now = datetime.now(UTC)
    oauth = {"token": "tk", "refresh_token": "rf"}
    api_row = (
        encrypt_dict(oauth),
        {"google_email": "x@y", "calendar_id": "primary", "timezone": "UTC"},
        True,
        now,
        now,
    )
    pool, conn = _mock_pool(api_row)
    out = await read_unified(pool, empresa_id=1)
    assert out is not None
    assert out["source"] == "api_connection"
    assert out["google_email"] == "x@y"
    assert out["oauth_credentials_json"] == oauth
    # Só 1 SELECT (não chamou fallback)
    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_read_fallback_legacy_quando_api_vazio():
    """api_connection vazio → consulta legacy."""
    now = datetime.now(UTC)
    legacy_row = (
        {"token": "tk-legacy"},
        "legacy@y",
        "cal_id_legacy",
        "America/Sao_Paulo",
        True,
        "+5567999",
        now,
        now,
    )
    pool, conn = _mock_pool(None, legacy_row)
    out = await read_unified(pool, empresa_id=1)
    assert out is not None
    assert out["source"] == "empresa_calendar_config"
    assert out["google_email"] == "legacy@y"
    assert out["calendar_id"] == "cal_id_legacy"
    assert out["aprovador_telefone"] == "+5567999"


@pytest.mark.asyncio
async def test_read_none_quando_ambos_vazios():
    pool, _ = _mock_pool(None, None)
    out = await read_unified(pool, empresa_id=999)
    assert out is None


# ---------- upsert_credentials_dual ----------


@pytest.mark.asyncio
async def test_upsert_escreve_em_ambos_storages():
    """Confirma INSERT em api_connection + empresa_calendar_config."""
    pool, conn = _mock_pool(None, None)  # nenhum extra existente
    await upsert_credentials_dual(
        pool,
        empresa_id=1,
        oauth_credentials_json={"token": "abc", "refresh_token": "def"},
        google_email="x@y",
    )
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("INSERT INTO api_connection" in s for s in sql_calls)
    assert any("INSERT INTO empresa_calendar_config" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_upsert_cifra_credenciais_no_api_connection():
    """access_token plaintext NÃO pode aparecer nos args do INSERT api_connection."""
    pool, conn = _mock_pool(None, None)
    await upsert_credentials_dual(
        pool,
        empresa_id=1,
        oauth_credentials_json={"token": "PLAINTEXT_TOKEN_XYZ"},
        google_email="x@y",
    )
    api_insert = next(
        c for c in conn.execute.await_args_list
        if "INSERT INTO api_connection" in c.args[0]
    )
    args = api_insert.args[1]
    # Token plain NÃO está nos args
    assert "PLAINTEXT_TOKEN_XYZ" not in str(args)
    # Mas algum arg é Fernet token
    assert any(isinstance(a, str) and a.startswith("gAAAAA") for a in args)


# ---------- refresh_credentials_dual ----------


@pytest.mark.asyncio
async def test_refresh_atualiza_ambos():
    pool, conn = _mock_pool()
    await refresh_credentials_dual(
        pool, empresa_id=1, oauth_credentials_json={"token": "novo"}
    )
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("UPDATE api_connection" in s for s in sql_calls)
    assert any("UPDATE empresa_calendar_config" in s for s in sql_calls)


# ---------- update_setting_dual ----------


@pytest.mark.asyncio
async def test_update_setting_calendar_id_atualiza_ambos():
    pool, conn = _mock_pool()
    ok = await update_setting_dual(
        pool, empresa_id=1, calendar_id="novo_id"
    )
    assert ok is True
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    # api_connection: merge JSONB
    assert any("UPDATE api_connection" in s and "extra_config" in s for s in sql_calls)
    # empresa_calendar_config: coluna direta
    assert any(
        "UPDATE empresa_calendar_config" in s and "calendar_id = %s" in s
        for s in sql_calls
    )


@pytest.mark.asyncio
async def test_update_setting_aprovador_vazia_string_eh_none():
    """aprovador_telefone='' deve virar NULL (desativa fluxo)."""
    pool, conn = _mock_pool()
    await update_setting_dual(
        pool, empresa_id=1, aprovador_telefone=""
    )
    legacy_update = next(
        c for c in conn.execute.await_args_list
        if "UPDATE empresa_calendar_config" in c.args[0]
    )
    args = legacy_update.args[1]
    # 1º arg é aprovador_telefone → deve ser None
    assert args[0] is None


@pytest.mark.asyncio
async def test_update_setting_sem_args_retorna_false():
    pool, conn = _mock_pool()
    ok = await update_setting_dual(pool, empresa_id=1)
    assert ok is False
    conn.execute.assert_not_awaited()


# ---------- delete_dual ----------


@pytest.mark.asyncio
async def test_delete_em_ambos():
    # Cada DELETE returna lista (fetchall) — mock 2 listas vazias = nada apagado
    pool, conn = _mock_pool([], [])
    ok = await delete_dual(pool, empresa_id=999)
    # Ambos vazios → False
    assert ok is False
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("DELETE FROM api_connection" in s for s in sql_calls)
    assert any("DELETE FROM empresa_calendar_config" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_delete_retorna_true_se_legacy_apagou():
    pool, _ = _mock_pool([], [(1,)])  # api_connection vazio, legacy retornou
    ok = await delete_dual(pool, empresa_id=1)
    assert ok is True


# ---------- migrate_legacy_to_api_connection ----------


@pytest.mark.asyncio
async def test_migrate_skip_empresas_ja_em_api_connection():
    """SELECT JOIN NOT EXISTS filtra já-migradas — só faz INSERT pra novas."""
    from whatsapp_langchain.integrations.google_calendar_storage import (
        migrate_legacy_to_api_connection,
    )

    # SELECT inicial retorna 2 rows (não-migradas)
    now = datetime.now(UTC)
    rows = [
        (10, {"token": "t1"}, "a@b", "primary", "UTC", None, True, "u1"),
        (20, {"token": "t2"}, "c@d", "cal-x", "BRT", "+55", True, "u2"),
    ]
    pool, conn = _mock_pool(rows)
    result = await migrate_legacy_to_api_connection(pool)
    assert result["migrated"] == 2
    assert result["skipped"] == 0
    assert result["total_legacy"] == 2


def test_provider_slug_constante():
    assert PROVIDER_SLUG == "google_calendar"
