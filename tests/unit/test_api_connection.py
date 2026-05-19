"""Testes do CRUD genérico api_connection (Sprint Conector API)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from whatsapp_langchain.integrations.api_connection import (
    create_conexao,
    delete_conexao,
    get_credenciais_decrypted,
    list_conexoes,
    record_test_result,
    update_conexao,
)
from whatsapp_langchain.integrations.crypto import (
    IntegracaoConfigError,
    encrypt_dict,
)
from whatsapp_langchain.integrations.providers import (
    PROVIDERS,
    get_provider,
    list_providers,
    validate_credentials_dict,
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


# ---------- providers catalog ----------


def test_catalogo_tem_4_providers():
    assert set(PROVIDERS.keys()) == {"wareline", "google_calendar", "asaas", "custom"}


def test_providers_validos_modelo_pydantic():
    """Todos PROVIDERS validam pelo ProviderSpec sem erro."""
    for slug, p in PROVIDERS.items():
        assert p.slug == slug
        assert p.nome
        assert p.descricao


def test_list_providers_skip_legacy():
    """include_legacy=False omite wareline + google_calendar."""
    non_legacy = list_providers(include_legacy=False)
    slugs = {p.slug for p in non_legacy}
    assert "wareline" not in slugs
    assert "google_calendar" not in slugs
    assert "asaas" in slugs
    assert "custom" in slugs


def test_get_provider_desconhecido_retorna_none():
    assert get_provider("inexistente-xyz") is None


def test_validate_credentials_asaas_requer_access_token():
    ok, msg = validate_credentials_dict("asaas", {"ambiente": "sandbox"})
    assert not ok
    assert msg is not None and "Access Token" in msg


def test_validate_credentials_asaas_ok():
    ok, msg = validate_credentials_dict(
        "asaas", {"access_token": "x", "ambiente": "sandbox"}
    )
    assert ok
    assert msg is None


def test_validate_credentials_provider_desconhecido():
    ok, msg = validate_credentials_dict("inexistente", {})
    assert not ok
    assert "desconhecido" in (msg or "").lower()


# ---------- list_conexoes ----------


@pytest.mark.asyncio
async def test_list_conexoes_enriquece_com_provider_info():
    now = datetime.now(UTC)
    row = (
        42,
        "asaas",
        "Asaas Prod",
        "https://api.asaas.com/v3",
        "api_key",
        {"ambiente": "producao"},
        True,
        None,
        None,
        None,
        now,
        now,
    )
    pool, _ = _mock_pool([row])
    out = await list_conexoes(pool, empresa_id=1)
    assert len(out) == 1
    assert out[0]["provider_nome"] == "Asaas"
    assert out[0]["provider_icone"] == "Receipt"


# ---------- create_conexao ----------


@pytest.mark.asyncio
async def test_create_conexao_provider_legacy_rejeita():
    pool, _ = _mock_pool()
    with pytest.raises(IntegracaoConfigError) as exc_info:
        await create_conexao(
            pool,
            empresa_id=1,
            provider_slug="wareline",  # legacy
            label="X",
            credentials={"username": "x", "password": "y", "client_id": "z", "client_secret": "w"},
        )
    assert "legacy" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_create_conexao_provider_desconhecido_rejeita():
    pool, _ = _mock_pool()
    with pytest.raises(IntegracaoConfigError):
        await create_conexao(
            pool,
            empresa_id=1,
            provider_slug="inexistente",
            label="X",
            credentials={},
        )


@pytest.mark.asyncio
async def test_create_conexao_credenciais_incompletas_rejeita():
    pool, _ = _mock_pool()
    with pytest.raises(IntegracaoConfigError):
        await create_conexao(
            pool,
            empresa_id=1,
            provider_slug="asaas",
            label="X",
            credentials={"ambiente": "sandbox"},  # falta access_token
        )


@pytest.mark.asyncio
async def test_create_conexao_asaas_ok():
    # INSERT returna id, depois SELECT pro safe_view
    now = datetime.now(UTC)
    safe_view_row = (
        99,
        "asaas",
        "Asaas Test",
        "https://api.asaas.com/v3",
        "api_key",
        encrypt_dict({"access_token": "tk", "ambiente": "sandbox"}),
        {},
        True,
        None,
        None,
        None,
        now,
        now,
    )
    pool, conn = _mock_pool((99,), safe_view_row)
    out = await create_conexao(
        pool,
        empresa_id=1,
        provider_slug="asaas",
        label="Asaas Test",
        credentials={"access_token": "tk", "ambiente": "sandbox"},
    )
    assert out["id"] == 99
    # Credenciais sensíveis vêm mascaradas
    assert out["credentials"]["access_token"] == "••••••••"
    # Verifica que INSERT recebeu credenciais CIFRADAS
    insert_call = next(
        c for c in conn.execute.await_args_list if "INSERT INTO api_connection" in c.args[0]
    )
    args_insert = insert_call.args[1]
    # access_token plaintext NÃO pode estar nos args
    assert "tk" not in args_insert
    # Pelo menos um arg deve ser Fernet (começa com gAAAAA)
    assert any(isinstance(a, str) and a.startswith("gAAAAA") for a in args_insert)


@pytest.mark.asyncio
async def test_create_conexao_custom_auth_type_resolvido_de_creds():
    """Custom: auth_type=dynamic → resolve via campo auth_method."""
    now = datetime.now(UTC)
    safe_view_row = (
        100,
        "custom",
        "Minha API",
        "https://api.exemplo.com",
        "bearer",  # auth_type resolvido
        encrypt_dict({"base_url": "https://api.exemplo.com", "auth_method": "bearer", "token": "tk"}),
        {},
        True,
        None,
        None,
        None,
        now,
        now,
    )
    pool, conn = _mock_pool((100,), safe_view_row)
    out = await create_conexao(
        pool,
        empresa_id=1,
        provider_slug="custom",
        label="Minha API",
        credentials={
            "base_url": "https://api.exemplo.com",
            "auth_method": "bearer",
            "token": "tk",
        },
    )
    assert out["auth_type"] == "bearer"


# ---------- get_credenciais_decrypted ----------


@pytest.mark.asyncio
async def test_get_credenciais_decrypted_round_trip():
    pool, _ = _mock_pool((encrypt_dict({"foo": "bar", "x": 42}),))
    creds = await get_credenciais_decrypted(pool, connection_id=1)
    assert creds == {"foo": "bar", "x": 42}


@pytest.mark.asyncio
async def test_get_credenciais_decrypted_none_se_inexistente():
    pool, _ = _mock_pool(None)
    creds = await get_credenciais_decrypted(pool, connection_id=999)
    assert creds is None


# ---------- update_conexao ----------


@pytest.mark.asyncio
async def test_update_conexao_404_se_outra_empresa():
    pool, _ = _mock_pool(None)
    out = await update_conexao(
        pool, connection_id=1, empresa_id=99, label="X"
    )
    assert out is None


@pytest.mark.asyncio
async def test_update_conexao_patch_password_invalida_cache():
    """Quando credentials_patch muda, deve DELETE no token cache."""
    now = datetime.now(UTC)
    initial_creds = encrypt_dict({"access_token": "old", "ambiente": "sandbox"})
    select_row = ("asaas", initial_creds, "https://api.asaas.com/v3")
    update_row = (1,)
    safe_view_row = (
        1,
        "asaas",
        "Asaas",
        "https://api.asaas.com/v3",
        "api_key",
        encrypt_dict({"access_token": "new", "ambiente": "sandbox"}),
        {},
        True,
        None,
        None,
        None,
        now,
        now,
    )
    pool, conn = _mock_pool(select_row, update_row, safe_view_row)
    await update_conexao(
        pool,
        connection_id=1,
        empresa_id=1,
        credentials_patch={"access_token": "new"},
    )
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    # Deve ter DELETE no token cache
    assert any(
        "DELETE FROM api_connection_token_cache" in s for s in sql_calls
    )


# ---------- delete + record_test_result ----------


@pytest.mark.asyncio
async def test_delete_conexao_ok():
    pool, _ = _mock_pool((1,))
    ok = await delete_conexao(pool, connection_id=1, empresa_id=1)
    assert ok is True


@pytest.mark.asyncio
async def test_delete_conexao_404():
    pool, _ = _mock_pool(None)
    ok = await delete_conexao(pool, connection_id=999, empresa_id=1)
    assert ok is False


@pytest.mark.asyncio
async def test_record_test_result_ok_zera_erro():
    pool, conn = _mock_pool()
    await record_test_result(
        pool, connection_id=1, ok=True, mensagem=None
    )
    args = conn.execute.await_args.args[1]
    assert args == (True, None, 1)


@pytest.mark.asyncio
async def test_record_test_result_erro_grava_mensagem():
    pool, conn = _mock_pool()
    await record_test_result(
        pool, connection_id=1, ok=False, mensagem="rede caiu"
    )
    args = conn.execute.await_args.args[1]
    assert args == (False, "rede caiu", 1)
