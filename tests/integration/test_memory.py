"""Testes de integração para memória semântica.

Verifica o fluxo completo de salvar e recuperar memórias usando
InMemoryStore (sem PostgreSQL, sem embeddings — busca por texto).

Executar com: pytest tests/integration/test_memory.py -v
"""

import pytest
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import SecretStr

from whatsapp_langchain.agents.tools import read_memory, save_memory


@pytest.fixture
def model(live_openrouter_api_key):
    """Modelo configurado para testes."""
    return ChatOpenAI(
        model="x-ai/grok-4.1-fast",
        api_key=SecretStr(live_openrouter_api_key),
        base_url="https://openrouter.ai/api/v1",
    )


class TestMemorySaveAndRecall:
    """Testa o fluxo completo: salvar memória → recuperar em nova conversa."""

    async def test_save_memory_tool_is_called(self, model):
        """Agente deve usar save_memory quando informação importante surge."""
        store = InMemoryStore()
        checkpointer = MemorySaver()

        agent = create_agent(
            model=model,
            tools=[save_memory, read_memory],
            system_prompt=(
                "Você é um assistente. Quando o usuário disser algo "
                "importante sobre si mesmo (nome, preferências), "
                "use save_memory para salvar. "
                "Quando precisar lembrar algo do usuário, use read_memory. "
                "Responda brevemente."
            ),
            middleware=[],
            checkpointer=checkpointer,
            store=store,
        )

        # Envia informação pessoal — agente deve chamar save_memory
        # ainvoke porque save_memory é async (usa await store.aput)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="Meu nome é João e eu adoro Python.")]},
            config={
                "configurable": {
                    "thread_id": "test-save-1",
                    "user_id": "+5511999999999",
                }
            },
        )

        assert result is not None
        assert "messages" in result

        # Verifica que a memória foi salva no store
        # Namespace: (user_id, "memories")
        items = store.search(("+5511999999999", "memories"))
        assert len(items) > 0

        # Pelo menos uma memória deve conter "João" ou "Python"
        saved_memories = [item.value["memory"] for item in items]
        all_text = " ".join(saved_memories).lower()
        assert "joão" in all_text or "python" in all_text

    async def test_memory_persists_across_threads(self, model):
        """Memórias salvas em um thread devem existir no store global."""
        store = InMemoryStore()
        checkpointer = MemorySaver()

        agent = create_agent(
            model=model,
            tools=[save_memory, read_memory],
            system_prompt=(
                "Você é um assistente. Sempre use save_memory para "
                "salvar informações pessoais do usuário e use read_memory "
                "quando precisar recuperar essas informações. "
                "Responda em uma frase curta."
            ),
            middleware=[],
            checkpointer=checkpointer,
            store=store,
        )

        user_id = "+5511888888888"

        # Thread 1: salva informação
        # ainvoke porque save_memory é async (usa await store.aput)
        await agent.ainvoke(
            {"messages": [HumanMessage(content="Me chamo Maria.")]},
            config={
                "configurable": {
                    "thread_id": "thread-A",
                    "user_id": user_id,
                }
            },
        )

        # Verifica que memória existe no store (acessível de qualquer thread)
        items = store.search((user_id, "memories"))
        assert len(items) > 0

        # Thread 2 (diferente!) teria acesso ao mesmo store
        # O namespace é por user_id, não por thread_id
        items_same_user = store.search((user_id, "memories"))
        assert len(items_same_user) > 0
