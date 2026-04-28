"""Testes para tools de memória semântica."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from whatsapp_langchain.agents.tools.memory import read_memory, save_memory

save_memory_fn = save_memory.coroutine
read_memory_fn = read_memory.coroutine


def _make_runtime(*, user_id: str | None = "+5511999999999"):
    configurable = {"thread_id": "thread-test"}
    if user_id:
        configurable["user_id"] = user_id
    runtime = MagicMock()
    runtime.config = {"configurable": configurable}
    return runtime


def _memory_item(value):
    item = MagicMock()
    item.value = value
    return item


class TestSaveMemoryTool:
    """Testes para a tool save_memory."""

    def test_tool_has_correct_name(self):
        assert save_memory.name == "save_memory"

    def test_tool_has_memory_parameter(self):
        schema = save_memory.get_input_schema()
        assert "memory" in schema.model_fields

    def test_saves_memory_with_store_and_user(self):
        store = AsyncMock()
        runtime = _make_runtime(user_id="+5511888888888")

        result = asyncio.run(
            save_memory_fn("Usuário prefere Python", runtime=runtime, store=store)
        )

        assert "sucesso" in result.lower()
        store.aput.assert_called_once()
        namespace = store.aput.call_args[0][0]
        value = store.aput.call_args[0][2]
        assert namespace == ("+5511888888888", "memories")
        assert value["memory"] == "Usuário prefere Python"

    def test_returns_message_when_store_missing(self):
        runtime = _make_runtime()
        result = asyncio.run(save_memory_fn("Algo", runtime=runtime, store=None))
        assert "não está disponível" in result.lower()

    def test_returns_message_when_user_missing(self):
        store = AsyncMock()
        runtime = _make_runtime(user_id=None)
        result = asyncio.run(save_memory_fn("Algo", runtime=runtime, store=store))
        assert "user_id" in result.lower()
        store.aput.assert_not_called()


class TestReadMemoryTool:
    """Testes para a tool read_memory."""

    def test_tool_has_correct_name(self):
        assert read_memory.name == "read_memory"

    def test_tool_has_query_parameter(self):
        schema = read_memory.get_input_schema()
        assert "query" in schema.model_fields

    def test_reads_memory_successfully(self):
        store = AsyncMock()
        store.asearch.return_value = [
            _memory_item({"memory": "Nome: Maria"}),
            _memory_item({"memory": "Prefere respostas curtas"}),
        ]
        runtime = _make_runtime(user_id="+5511777777777")

        result = asyncio.run(
            read_memory_fn("quem é o usuário", limit=5, runtime=runtime, store=store)
        )

        assert "memórias relevantes" in result.lower()
        assert "nome: maria" in result.lower()
        assert "prefere respostas curtas" in result.lower()
        store.asearch.assert_called_once()
        namespace = store.asearch.call_args[0][0]
        assert namespace == ("+5511777777777", "memories")

    def test_clamps_limit(self):
        store = AsyncMock()
        store.asearch.return_value = [_memory_item({"memory": "ok"})]
        runtime = _make_runtime()

        asyncio.run(read_memory_fn("consulta", limit=999, runtime=runtime, store=store))
        assert store.asearch.call_args.kwargs["limit"] == 10

    def test_returns_message_when_query_empty(self):
        store = AsyncMock()
        runtime = _make_runtime()
        result = asyncio.run(read_memory_fn("  ", runtime=runtime, store=store))
        assert "consulta" in result.lower()
        store.asearch.assert_not_called()

    def test_returns_message_when_no_results(self):
        store = AsyncMock()
        store.asearch.return_value = []
        runtime = _make_runtime()
        result = asyncio.run(
            read_memory_fn("sem resultado", runtime=runtime, store=store)
        )
        assert "nenhuma memória relevante" in result.lower()

    def test_returns_message_when_store_missing(self):
        runtime = _make_runtime()
        result = asyncio.run(read_memory_fn("query", runtime=runtime, store=None))
        assert "não está disponível" in result.lower()
