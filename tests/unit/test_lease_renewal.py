"""R7 — renovação de lease (fencing) + heartbeat do worker.

Mock-based (sem DB). A concorrência real (reclaim entre workers) é coberta por
teste de integração com Postgres; aqui validamos o contrato SQL, o fence por
attempts e a parada do heartbeat ao perder a propriedade.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from whatsapp_langchain.shared.queue import renew_lease


def _pool(fetch_row):
    conn = AsyncMock()
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=fetch_row)
    conn.execute = AsyncMock(return_value=cur)
    pool = AsyncMock()

    @asynccontextmanager
    async def fake_conn():
        yield conn

    pool.connection = fake_conn
    return pool, conn


async def test_renew_lease_still_owner():
    """Renova e retorna True quando ainda é o dono (UPDATE afeta 1 linha)."""
    pool, conn = _pool((123,))
    ok = await renew_lease(pool, 123, attempts=1, lease_seconds=180)
    assert ok is True
    sql = conn.execute.call_args[0][0]
    params = conn.execute.call_args[0][1]
    # fence: só renova se ainda for o dono (attempts) e ainda processando
    assert "attempts = %s" in sql
    assert "status = 'processing'" in sql
    assert "lease_until" in sql
    assert params == (180, 123, 1)


async def test_renew_lease_lost_ownership():
    """Retorna False quando o UPDATE não afeta linha (foi reclaimado)."""
    pool, _ = _pool(None)
    ok = await renew_lease(pool, 123, attempts=1, lease_seconds=180)
    assert ok is False


async def test_heartbeat_para_ao_perder_propriedade(monkeypatch):
    """O heartbeat renova e PARA assim que perde o lease (não loopa infinito)."""
    from whatsapp_langchain.worker import main as worker_main

    calls = []

    async def fake_renew(pool, mid, attempts, lease):
        calls.append((mid, attempts))
        return False  # perdeu o lease já na 1ª renovação

    async def fast_sleep(_s):
        return

    monkeypatch.setattr(worker_main, "renew_lease", fake_renew)
    monkeypatch.setattr(worker_main.asyncio, "sleep", fast_sleep)

    msg = SimpleNamespace(id=7, attempts=2)
    await worker_main._lease_heartbeat(object(), msg)  # retorna ao perder o dono

    assert calls == [(7, 2)]
