"""Testes do módulo integrations/wareline/credentials.py.

Foca em: cripto Fernet (round-trip), CRUD com mock pool, validação
de chave ausente.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from whatsapp_langchain.integrations.wareline.credentials import (
    decrypt,
    delete_credentials,
    encrypt,
    get_credentials,
    get_credentials_safe_view,
    record_test_result,
    save_credentials,
    update_credentials_partial,
)
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineConfigError,
)


@pytest.fixture
def fernet_key() -> str:
    """Gera chave Fernet pra tests + patcha em settings."""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _patch_fernet_key(fernet_key, monkeypatch):
    """Auto-aplica chave fake em settings pra todos os tests do módulo."""
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "wareline_encryption_key", SecretStr(fernet_key))


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------- Cripto ----------


def test_encrypt_decrypt_round_trip():
    plaintext = "minha-senha-super-secreta-com-acentos-éàç"
    cipher = encrypt(plaintext)
    assert cipher != plaintext
    assert decrypt(cipher) == plaintext


def test_decrypt_corrompido_levanta_config_error():
    with pytest.raises(WarelineConfigError):
        decrypt("nao-eh-fernet-valido")


def test_encrypt_sem_chave_levanta_config_error(monkeypatch):
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "wareline_encryption_key", None)
    with pytest.raises(WarelineConfigError) as exc_info:
        encrypt("foo")
    assert "WARELINE_ENCRYPTION_KEY" in str(exc_info.value)


# ---------- CRUD ----------


@pytest.mark.asyncio
async def test_get_credentials_retorna_none_se_inexistente():
    pool, _ = _mock_pool(None)
    creds = await get_credentials(pool, empresa_id=42)
    assert creds is None


@pytest.mark.asyncio
async def test_get_credentials_decifra_password_e_secret():
    pwd_enc = encrypt("senha123")
    secret_enc = encrypt("super-secret")
    row = (
        "https://modulos.conectew.com.br",
        "https://services.conectew.com.br",
        "user1",
        pwd_enc,
        "client1",
        secret_enc,
        True,
    )
    pool, _ = _mock_pool(row)
    creds = await get_credentials(pool, empresa_id=1)
    assert creds is not None
    assert creds.empresa_id == 1
    assert creds.username == "user1"
    assert creds.password == "senha123"  # decifrado
    assert creds.client_id == "client1"
    assert creds.client_secret == "super-secret"
    assert creds.ativo is True


@pytest.mark.asyncio
async def test_get_credentials_safe_view_nao_expoe_senhas():
    now = datetime.now(UTC)
    row = (
        "https://modulos.conectew.com.br",
        "https://services.conectew.com.br",
        "user1",
        "client1",
        True,
        now,
        True,
        None,
        now,
    )
    pool, _ = _mock_pool(row)
    view = await get_credentials_safe_view(pool, empresa_id=1)
    assert view is not None
    # Senhas nunca aparecem
    assert "password" not in view or view.get("password") is None
    assert "client_secret" not in view or view.get("client_secret") is None
    # Mas tem flags indicando que estão configuradas
    assert view["password_set"] is True
    assert view["client_secret_set"] is True
    assert view["username"] == "user1"
    assert view["ultimo_teste_ok"] is True


@pytest.mark.asyncio
async def test_save_credentials_cripto_password_e_secret():
    # 1ª chamada (execute INSERT) + 2ª (DELETE token cache) + safe view final
    # safe_view faz outro SELECT — usamos side_effect na fetchone
    now = datetime.now(UTC)
    view_row = (
        "https://modulos.conectew.com.br",
        "https://services.conectew.com.br",
        "user-x",
        "client-x",
        True,
        None,
        None,
        None,
        now,
    )
    pool, conn = _mock_pool(view_row)
    result = await save_credentials(
        pool,
        empresa_id=1,
        username="user-x",
        password="senha-plain",
        client_id="client-x",
        client_secret="secret-plain",
    )
    assert result["username"] == "user-x"
    # Confirma que INSERT recebeu senha CIFRADA (não plain)
    insert_call = next(
        c for c in conn.execute.await_args_list if "INSERT INTO wareline_credentials" in c.args[0]
    )
    args = insert_call.args[1]
    # senha plain "senha-plain" não pode aparecer nos args
    assert "senha-plain" not in args
    assert "secret-plain" not in args
    # Pelo menos um arg deve ser ciphertext (começa com gAAAAA — Fernet token)
    assert any(isinstance(a, str) and a.startswith("gAAAAA") for a in args)


@pytest.mark.asyncio
async def test_update_credentials_partial_sem_password_preserva():
    # Update parcial só do username — DELETE token cache NÃO deve rolar
    # (senha não trocou)
    view_row = (
        "https://modulos.conectew.com.br",
        "https://services.conectew.com.br",
        "novo-user",
        "client-1",
        True,
        None,
        None,
        None,
        datetime.now(UTC),
    )
    pool, conn = _mock_pool(("1",), view_row)
    result = await update_credentials_partial(
        pool, empresa_id=1, username="novo-user"
    )
    assert result is not None
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    # DELETE no token_cache só deve ocorrer se password/secret trocou
    assert not any("DELETE FROM wareline_token_cache" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_delete_credentials_returns_true_quando_existia():
    pool, _ = _mock_pool((1,))
    ok = await delete_credentials(pool, empresa_id=1)
    assert ok is True


@pytest.mark.asyncio
async def test_delete_credentials_returns_false_quando_inexistente():
    pool, _ = _mock_pool(None)
    ok = await delete_credentials(pool, empresa_id=999)
    assert ok is False


@pytest.mark.asyncio
async def test_record_test_result_ok_zera_erro():
    pool, conn = _mock_pool()
    await record_test_result(pool, empresa_id=1, ok=True, mensagem=None)
    sql = conn.execute.await_args.args[0]
    assert "UPDATE wareline_credentials" in sql
    assert "ultimo_teste_at = NOW()" in sql
    args = conn.execute.await_args.args[1]
    # ok=True → ultimo_teste_erro = None
    assert args == (True, None, 1)


@pytest.mark.asyncio
async def test_record_test_result_erro_grava_mensagem():
    pool, conn = _mock_pool()
    await record_test_result(
        pool, empresa_id=1, ok=False, mensagem="Token inválido"
    )
    args = conn.execute.await_args.args[1]
    assert args == (False, "Token inválido", 1)
