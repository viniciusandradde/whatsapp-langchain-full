"""Testes dos helpers de multi-tenancy + dependency get_empresa_context."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
)
from whatsapp_langchain.shared.empresa import (
    get_default_empresa_id,
    get_empresa_membership,
    is_superadmin,
    list_empresas_of_user,
)


def _mock_request(headers: dict[str, str]) -> Request:
    """Builda Request mínimo com headers pro dependency rodar."""
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "method": "GET",
        "path": "/test",
        "query_string": b"",
    }
    return Request(scope)


def _mock_pool(*fetchone_results) -> MagicMock:
    cur = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=list(fetchone_results))
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# === Helpers em shared/empresa.py ===


async def test_list_empresas_returns_empty_when_no_membership():
    cur = AsyncMock()
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    empresas = await list_empresas_of_user(pool, "user-x")
    assert empresas == []


async def test_get_default_empresa_id_returns_id_when_member():
    pool = _mock_pool((42,))
    eid = await get_default_empresa_id(pool, "user-x")
    assert eid == 42


async def test_get_default_empresa_id_none_when_no_membership():
    pool = _mock_pool(None)
    assert await get_default_empresa_id(pool, "user-x") is None


async def test_get_empresa_membership_returns_record():
    now = datetime.now(UTC)
    pool = _mock_pool((1, "user-x", "admin", True, now))
    m = await get_empresa_membership(pool, 1, "user-x")
    assert m is not None
    assert m.role == "admin"
    assert m.is_default is True


async def test_is_superadmin_true_when_flag_set():
    pool = _mock_pool((True,))
    assert await is_superadmin(pool, "user-x") is True


async def test_is_superadmin_false_when_user_missing():
    pool = _mock_pool(None)
    assert await is_superadmin(pool, "user-x") is False


# === get_user_id_from_request ===


def test_user_id_from_header():
    req = _mock_request({"x-user-id": "abc-123"})
    assert get_user_id_from_request(req) == "abc-123"


def test_user_id_missing_raises_401():
    req = _mock_request({})
    with pytest.raises(HTTPException) as exc:
        get_user_id_from_request(req)
    assert exc.value.status_code == 401


# === get_empresa_context dependency ===


async def test_empresa_context_falls_back_to_default():
    """Sem X-Empresa-Id → usa empresa default do user."""
    pool = _mock_pool((7,))
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        req = _mock_request({"x-user-id": "user-x"})
        empresa_id = await get_empresa_context(req)
    assert empresa_id == 7


async def test_empresa_context_uses_header_when_member():
    """Header X-Empresa-Id válido (user é membro) → retorna o do header."""
    now = datetime.now(UTC)
    # primeira fetchone: is_superadmin → False
    # segunda fetchone: get_empresa_membership → row do membro
    pool = _mock_pool((False,), (3, "user-x", "operator", False, now))
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        req = _mock_request({"x-user-id": "user-x", "x-empresa-id": "3"})
        empresa_id = await get_empresa_context(req)
    assert empresa_id == 3


async def test_empresa_context_403_when_not_member():
    """Header pra empresa onde user NÃO é membro (e não é superadmin)."""
    pool = _mock_pool((False,), None)  # is_superadmin=False, membership=None
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        req = _mock_request({"x-user-id": "user-x", "x-empresa-id": "9"})
        with pytest.raises(HTTPException) as exc:
            await get_empresa_context(req)
    assert exc.value.status_code == 403


async def test_empresa_context_superadmin_bypasses_membership():
    """Superadmin pode entrar em qualquer empresa via header."""
    pool = _mock_pool((True,))  # is_superadmin=True
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        req = _mock_request({"x-user-id": "user-x", "x-empresa-id": "99"})
        empresa_id = await get_empresa_context(req)
    assert empresa_id == 99


async def test_empresa_context_403_when_no_membership_at_all():
    """User sem nenhuma empresa → 403."""
    pool = _mock_pool(None)  # default empresa não existe
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        req = _mock_request({"x-user-id": "ghost"})
        with pytest.raises(HTTPException) as exc:
            await get_empresa_context(req)
    assert exc.value.status_code == 403


async def test_empresa_context_invalid_header_400():
    """X-Empresa-Id não numérico → 400."""
    req = _mock_request({"x-user-id": "user-x", "x-empresa-id": "abc"})
    with patch(
        "whatsapp_langchain.server.dependencies.get_pool",
        new=AsyncMock(return_value=MagicMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_empresa_context(req)
    assert exc.value.status_code == 400
