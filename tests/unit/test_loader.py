"""Testes do agent loader — carregamento dinâmico de agentes."""

import pytest
from langgraph.store.memory import InMemoryStore

from whatsapp_langchain.agents.loader import (
    AgentNotFoundError,
    list_agents,
    load_graph,
)


class TestListAgents:
    """Testes de listagem de agentes."""

    def test_lists_vsa_tech(self):
        """Deve encontrar o agente vsa_tech no catálogo."""
        agents = list_agents()
        assert "vsa_tech" in agents

    def test_returns_list(self):
        """Deve retornar uma lista de strings."""
        agents = list_agents()
        assert isinstance(agents, list)
        for agent in agents:
            assert isinstance(agent, str)


class TestLoadGraph:
    """Testes de carregamento de agentes."""

    async def test_load_vsa_tech(self):
        """Deve carregar o agente vsa_tech com sucesso."""
        graph = await load_graph("vsa_tech")
        assert graph is not None

    async def test_load_vsa_tech_with_store(self):
        """Deve carregar o agente com store para memória semântica."""
        store = InMemoryStore()
        graph = await load_graph("vsa_tech", store=store)
        assert graph is not None

    async def test_load_nonexistent_agent(self):
        """Deve falhar com AgentNotFoundError para agente inexistente."""
        with pytest.raises(AgentNotFoundError) as exc_info:
            await load_graph("agente_que_nao_existe")
        assert exc_info.value.agent_id == "agente_que_nao_existe"

    def test_agent_not_found_error_message(self):
        """AgentNotFoundError deve conter o agent_id na mensagem."""
        error = AgentNotFoundError("test_agent")
        assert "test_agent" in str(error)
