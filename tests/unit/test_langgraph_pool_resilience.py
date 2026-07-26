"""Regressão: checkpointer/store do LangGraph precisam sobreviver a restart do PG.

Contexto (incidente 2026-07-26): `open_checkpointer()`/`open_store()` usavam
`from_conn_string()` sem pool, que abre UMA `AsyncConnection` crua e a mantém
pela vida inteira do worker. Quando o Postgres crashou (crash recovery derruba
todas as conexões), essa conexão morreu e nunca mais voltou — o worker virou
zumbi: continuava consumindo a fila (o pool da app reconecta sozinho) mas TODA
mensagem que chegava no agente falhava com `OperationalError: the connection is
closed`, retry 3x, `failed`. ~40h sem responder cliente, com o container `Up` e
`restarts=0`.

O contrato defendido aqui: os dois são respaldados por `AsyncConnectionPool`
(que reabre conexão sob demanda), nunca por uma `AsyncConnection` única.
"""

import pytest
from psycopg import AsyncConnection

from whatsapp_langchain.shared import db as db_module


class _FakePool:
    """Stand-in de AsyncConnectionPool que não toca em rede."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.conninfo = args[0] if args else kwargs.get("conninfo")
        self.kwargs = kwargs.get("kwargs", {})
        self.closed = False

    async def open(self) -> None: ...

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> "_FakePool":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


@pytest.fixture(autouse=True)
def _sem_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pool fake + conexão única proibida.

    Qualquer tentativa de abrir `AsyncConnection` direto falha com mensagem
    explícita — é exatamente o padrão que causou o incidente.
    """
    monkeypatch.setattr(db_module, "AsyncConnectionPool", _FakePool)

    async def _proibido(*args: object, **kwargs: object) -> None:
        msg = (
            "AsyncConnection.connect direto: LangGraph precisa de pool, "
            "senão a conexão morre no crash do Postgres e nunca reconecta"
        )
        raise AssertionError(msg)

    monkeypatch.setattr(AsyncConnection, "connect", _proibido)


async def test_checkpointer_usa_pool_e_nao_conexao_unica() -> None:
    """open_checkpointer entrega um saver respaldado por pool."""
    stack, checkpointer = await db_module.open_checkpointer()
    try:
        assert isinstance(checkpointer.conn, _FakePool), (
            "checkpointer precisa de pool (reconecta após crash do PG), "
            f"veio {type(checkpointer.conn).__name__}"
        )
        # LangGraph exige esses kwargs nas conexões entregues pelo pool.
        assert checkpointer.conn.kwargs["autocommit"] is True
        assert checkpointer.conn.kwargs["prepare_threshold"] == 0
        assert "row_factory" in checkpointer.conn.kwargs
    finally:
        await stack.aclose()


async def test_store_usa_pool_e_nao_conexao_unica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """open_store entrega um store respaldado por pool."""
    monkeypatch.setattr(db_module.settings, "memory_enabled", True)
    monkeypatch.setattr(db_module, "resolve_store_index_config", lambda: None)

    stack, store = await db_module.open_store()
    assert store is not None
    try:
        assert isinstance(store.conn, _FakePool), (
            "store precisa de pool (reconecta após crash do PG), "
            f"veio {type(store.conn).__name__}"
        )
    finally:
        await stack.aclose()  # type: ignore[union-attr]


async def test_pool_do_langgraph_e_separado_do_pool_da_app() -> None:
    """O pool do LangGraph não é o pool RLS/transacional da aplicação.

    O da app usa transações + `SET app.empresa_id`; o do LangGraph exige
    autocommit. Compartilhar quebra os dois.
    """
    stack, checkpointer = await db_module.open_checkpointer()
    try:
        assert checkpointer.conn is not db_module.pool, (
            "checkpointer não pode reusar o pool RLS da aplicação"
        )
    finally:
        await stack.aclose()


async def test_store_desligado_nao_abre_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEMORY_ENABLED=false continua retornando (None, None), sem I/O."""
    monkeypatch.setattr(db_module.settings, "memory_enabled", False)

    stack, store = await db_module.open_store()

    assert stack is None
    assert store is None
