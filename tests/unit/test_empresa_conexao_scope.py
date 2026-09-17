"""ADR-002, Etapa 4 — `is_conexao_scope_ativo` (o opt-in por empresa).

Só cobre a composição (linha lida → bool, empresa inexistente → False,
fail-closed por default). A query em si é trivial demais pra valer mock —
o que importa é o default seguro quando a empresa some.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.empresa import is_conexao_scope_ativo


def _pool_com_resultado(row):
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=row)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection = MagicMock(return_value=ctx)
    return pool


@pytest.mark.parametrize(
    ("row", "esperado"),
    [
        ((True,), True),
        ((False,), False),
        (None, False),  # empresa não existe — fail-closed, não fail-open
    ],
)
async def test_is_conexao_scope_ativo(row, esperado):
    pool = _pool_com_resultado(row)
    assert await is_conexao_scope_ativo(pool, empresa_id=1) is esperado
