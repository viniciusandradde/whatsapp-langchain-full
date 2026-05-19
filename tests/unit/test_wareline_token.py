"""Testes do token cache + refresh OAuth Wareline."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import respx
from cryptography.fernet import Fernet
from httpx import Response

from whatsapp_langchain.integrations.wareline.errors import (
    WarelineAuthError,
    WarelineConfigError,
    WarelineUnavailableError,
)
from whatsapp_langchain.integrations.wareline.token import (
    get_or_refresh_token,
    invalidate_token,
)


@pytest.fixture(autouse=True)
def _patch_fernet_key(monkeypatch):
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "wareline_encryption_key", SecretStr(key))


def _mock_pool(fetchone_results) -> tuple[MagicMock, AsyncMock]:
    """Helper: aceita lista de resultados sequenciais pra fetchone."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=fetchone_results)
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_cache_hit_retorna_sem_oauth():
    """Token em cache e válido → retorna direto, sem chamar OAuth."""
    future = datetime.now(UTC) + timedelta(seconds=200)
    cached_row = ("token-cacheado", future)
    pool, _ = _mock_pool([cached_row])
    token = await get_or_refresh_token(pool, empresa_id=1)
    assert token == "token-cacheado"


@pytest.mark.asyncio
@respx.mock
async def test_cache_miss_faz_oauth_e_persiste(monkeypatch):
    """Cache vazio → carrega creds → OAuth → INSERT no cache."""
    from whatsapp_langchain.integrations.wareline.credentials import encrypt
    from whatsapp_langchain.integrations.wareline.models import (
        WarelineCredentials,
    )

    # Patch get_credentials pra retornar fake creds (não bate DB)
    fake_creds = WarelineCredentials(
        empresa_id=1,
        base_url="https://modulos.test",
        pacientes_base_url="https://services.test",
        username="u",
        password="p",
        client_id="cid",
        client_secret="cs",
    )

    async def fake_get_creds(_pool, _eid):
        return fake_creds

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.token.get_credentials",
        fake_get_creds,
    )

    # Mock OAuth endpoint
    respx.post(
        "https://modulos.test/services/auth/realms/conectew/"
        "protocol/openid-connect/token"
    ).mock(
        return_value=Response(
            200,
            json={
                "access_token": "novo-token-xyz",
                "expires_in": 300,
                "refresh_expires_in": 3600,
                "refresh_token": "refresh-abc",
                "token_type": "Bearer",
                "scope": "default",
            },
        )
    )

    # Cache miss inicial
    pool, conn = _mock_pool([None])
    token = await get_or_refresh_token(pool, empresa_id=1)
    assert token == "novo-token-xyz"

    # Confirma INSERT no cache (com expires_at)
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any(
        "INSERT INTO wareline_token_cache" in s and "ON CONFLICT" in s
        for s in sql_calls
    )
    # Confirma que encrypt funciona (sanity test do cripto)
    assert encrypt("foo") != "foo"


@pytest.mark.asyncio
@respx.mock
async def test_oauth_401_levanta_auth_error(monkeypatch):
    from whatsapp_langchain.integrations.wareline.models import (
        WarelineCredentials,
    )

    async def fake_get_creds(_pool, _eid):
        return WarelineCredentials(
            empresa_id=1,
            base_url="https://modulos.test",
            pacientes_base_url="https://services.test",
            username="u",
            password="errada",
            client_id="cid",
            client_secret="cs",
        )

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.token.get_credentials",
        fake_get_creds,
    )

    respx.post(
        "https://modulos.test/services/auth/realms/conectew/"
        "protocol/openid-connect/token"
    ).mock(
        return_value=Response(
            401,
            json={"error": "invalid_grant"},
        )
    )
    pool, _ = _mock_pool([None])
    with pytest.raises(WarelineAuthError):
        await get_or_refresh_token(pool, empresa_id=1)


@pytest.mark.asyncio
@respx.mock
async def test_oauth_5xx_levanta_unavailable(monkeypatch):
    from whatsapp_langchain.integrations.wareline.models import (
        WarelineCredentials,
    )

    async def fake_get_creds(_pool, _eid):
        return WarelineCredentials(
            empresa_id=1,
            base_url="https://modulos.test",
            pacientes_base_url="https://services.test",
            username="u",
            password="p",
            client_id="cid",
            client_secret="cs",
        )

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.token.get_credentials",
        fake_get_creds,
    )
    respx.post(
        "https://modulos.test/services/auth/realms/conectew/"
        "protocol/openid-connect/token"
    ).mock(return_value=Response(503, text="upstream down"))
    pool, _ = _mock_pool([None])
    with pytest.raises(WarelineUnavailableError):
        await get_or_refresh_token(pool, empresa_id=1)


@pytest.mark.asyncio
async def test_sem_credenciais_levanta_config_error(monkeypatch):
    async def fake_get_creds(_pool, _eid):
        return None

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.token.get_credentials",
        fake_get_creds,
    )
    pool, _ = _mock_pool([None])
    with pytest.raises(WarelineConfigError):
        await get_or_refresh_token(pool, empresa_id=999)


@pytest.mark.asyncio
async def test_credentials_inativas_levanta_config_error(monkeypatch):
    from whatsapp_langchain.integrations.wareline.models import (
        WarelineCredentials,
    )

    async def fake_get_creds(_pool, _eid):
        return WarelineCredentials(
            empresa_id=1,
            base_url="https://modulos.test",
            pacientes_base_url="https://services.test",
            username="u",
            password="p",
            client_id="cid",
            client_secret="cs",
            ativo=False,  # desativado
        )

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.token.get_credentials",
        fake_get_creds,
    )
    pool, _ = _mock_pool([None])
    with pytest.raises(WarelineConfigError) as exc_info:
        await get_or_refresh_token(pool, empresa_id=1)
    assert "desativada" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_invalidate_token_apaga_cache():
    pool, conn = _mock_pool([])
    await invalidate_token(pool, empresa_id=1)
    sql = conn.execute.await_args.args[0]
    assert "DELETE FROM wareline_token_cache" in sql
