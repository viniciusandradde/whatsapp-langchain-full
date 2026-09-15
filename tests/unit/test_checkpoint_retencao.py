"""Retenção de checkpoints do LangGraph (Fase 2 do plano de 2026-09-15).

A correção do SQL ("só o último por thread") é provada contra um Postgres de
verdade no dev; aqui travamos o contrato do módulo: a trava de sessão serializa
os dois workers, a poda apaga writes antes de checkpoints, e uma thread ruim na
política 2 não derruba as outras.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared import checkpoint_retencao as cr

pytestmark = pytest.mark.asyncio


def _pool_com_conn(conn):
    pool = MagicMock()

    @asynccontextmanager
    async def _connection():
        yield conn

    pool.connection = _connection
    return pool


def _conn_execute(resultados):
    """conn.execute() devolve um cursor; `resultados` é uma fila de rowcount/row.

    Cada item vira o retorno de uma chamada, na ordem: um int vira `rowcount`,
    uma tupla vira `fetchone`.
    """
    chamadas = list(resultados)
    conn = AsyncMock()

    async def _execute(sql, params=None):
        cur = MagicMock()
        valor = chamadas.pop(0)
        if isinstance(valor, tuple):
            cur.fetchone = AsyncMock(return_value=valor)
            cur.fetchall = AsyncMock(return_value=[valor])
        else:
            cur.rowcount = valor
        return cur

    conn.execute = AsyncMock(side_effect=_execute)
    return conn


class TestPodaUltimoPorThread:
    async def test_apaga_writes_antes_de_checkpoints(self) -> None:
        conn = _conn_execute([12, 7])  # writes apagados, checkpoints apagados
        pool = _pool_com_conn(conn)
        r = await cr.podar_para_ultimo_por_thread(pool)
        assert r == {"writes_apagados": 12, "checkpoints_apagados": 7}
        # ordem: primeiro DELETE é em checkpoint_writes
        primeira_sql = conn.execute.await_args_list[0].args[0]
        segunda_sql = conn.execute.await_args_list[1].args[0]
        assert "checkpoint_writes" in primeira_sql
        assert "DELETE FROM checkpoints c" in segunda_sql
        # não toca checkpoint_blobs em nenhuma
        assert "checkpoint_blobs" not in primeira_sql + segunda_sql


class TestApagarThreadsEncerradas:
    async def test_chama_adelete_por_thread(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cr, "_threads_encerradas", AsyncMock(return_value=["a:x", "b:y", "c:z"])
        )
        ckpt = AsyncMock()
        r = await cr.apagar_threads_encerradas(ckpt, MagicMock(), dias=90)
        assert r == {"threads_encerradas_apagadas": 3}
        assert ckpt.adelete_thread.await_count == 3

    async def test_uma_thread_ruim_nao_para_o_resto(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cr, "_threads_encerradas", AsyncMock(return_value=["ok1", "ruim", "ok2"])
        )
        ckpt = AsyncMock()
        ckpt.adelete_thread = AsyncMock(side_effect=[None, RuntimeError("boom"), None])
        r = await cr.apagar_threads_encerradas(ckpt, MagicMock(), dias=90)
        assert r == {"threads_encerradas_apagadas": 2}


class TestRodarRetencao:
    async def test_sem_a_trava_nao_poda(self, monkeypatch) -> None:
        conn = _conn_execute([(False,)])  # pg_try_advisory_lock → False
        ckpt = MagicMock()
        ckpt.conn = _pool_com_conn(conn)
        podar = AsyncMock()
        monkeypatch.setattr(cr, "podar_para_ultimo_por_thread", podar)
        r = await cr.rodar_retencao(ckpt, MagicMock(), dias=90)
        assert r is None
        podar.assert_not_awaited()

    async def test_com_a_trava_roda_as_duas_politicas_e_solta(
        self, monkeypatch
    ) -> None:
        # execute: lock(True), [poda usa OUTRA conexão], unlock
        conn = _conn_execute([(True,), None])  # try_lock True, unlock
        ckpt = MagicMock()
        ckpt.conn = _pool_com_conn(conn)
        monkeypatch.setattr(
            cr,
            "podar_para_ultimo_por_thread",
            AsyncMock(return_value={"checkpoints_apagados": 5, "writes_apagados": 9}),
        )
        monkeypatch.setattr(
            cr,
            "apagar_threads_encerradas",
            AsyncMock(return_value={"threads_encerradas_apagadas": 2}),
        )
        r = await cr.rodar_retencao(ckpt, MagicMock(), dias=90)
        assert r == {
            "checkpoints_apagados": 5,
            "writes_apagados": 9,
            "threads_encerradas_apagadas": 2,
        }
        # soltou a trava (segunda chamada de execute é o unlock)
        assert "pg_advisory_unlock" in conn.execute.await_args_list[-1].args[0]
