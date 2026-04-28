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

    def test_lists_rhawk_assistant(self):
        """Deve encontrar o agente rhawk_assistant no catálogo."""
        agents = list_agents()
        assert "rhawk_assistant" in agents

    def test_returns_list(self):
        """Deve retornar uma lista de strings."""
        agents = list_agents()
        assert isinstance(agents, list)
        for agent in agents:
            assert isinstance(agent, str)


class TestLoadGraph:
    """Testes de carregamento de agentes."""

    def test_load_rhawk_assistant(self):
        """Deve carregar o agente rhawk_assistant com sucesso."""
        graph = load_graph("rhawk_assistant")
        assert graph is not None

    def test_load_rhawk_assistant_with_store(self):
        """Deve carregar o agente com store para memória semântica."""
        store = InMemoryStore()
        graph = load_graph("rhawk_assistant", store=store)
        assert graph is not None

    def test_load_nonexistent_agent(self):
        """Deve falhar com AgentNotFoundError para agente inexistente."""
        with pytest.raises(AgentNotFoundError) as exc_info:
            load_graph("agente_que_nao_existe")
        assert exc_info.value.agent_id == "agente_que_nao_existe"

    def test_agent_not_found_error_message(self):
        """AgentNotFoundError deve conter o agent_id na mensagem."""
        error = AgentNotFoundError("test_agent")
        assert "test_agent" in str(error)
