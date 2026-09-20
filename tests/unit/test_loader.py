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


class TestContextoTamanhoChegaAoBuildGraph:
    """ADR-004: o tier do agente vira `contexto_chars` no `build_graph`.

    Até 2026-09 `janela_memoria` era salvo e nunca chegava aqui — a UI
    prometia o que o worker ignorava. Estes testes são o que impede a
    regressão: o kwarg TEM que sair do loader.
    """

    @staticmethod
    def _runtime(**overrides):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        base = dict(
            slug="t",
            template_catalog="vsa_tech",
            prompt_override=None,
            modelo=None,
            temperatura=0.5,
            top_p=0.9,
            max_tokens=None,
            tools_enabled=[],
            base_conhecimento_ids=[],
        )
        base.update(overrides)
        return AgenteRuntime(**base)

    @staticmethod
    def _capturar(monkeypatch):
        import whatsapp_langchain.agents.catalog.vsa_tech.agent as mod

        chamadas: list[dict] = []

        def fake_build_graph(**kwargs):
            chamadas.append(kwargs)
            return object()

        monkeypatch.setattr(mod, "build_graph", fake_build_graph)
        return chamadas

    async def test_tier_vira_teto_em_caracteres(self, monkeypatch):
        chamadas = self._capturar(monkeypatch)
        await load_graph(
            "vsa_tech", agente_runtime=self._runtime(contexto_tamanho="extended")
        )
        assert chamadas[0]["contexto_chars"] == 300_000
        assert chamadas[0]["trim_keep_turns"] is None

    async def test_legado_sem_tier_fica_sem_teto(self, monkeypatch):
        chamadas = self._capturar(monkeypatch)
        await load_graph(
            "vsa_tech",
            agente_runtime=self._runtime(contexto_tamanho=None, janela_memoria=7),
        )
        assert chamadas[0]["contexto_chars"] is None
        assert chamadas[0]["trim_keep_turns"] == 7

    async def test_modo_legacy_sem_runtime(self, monkeypatch):
        chamadas = self._capturar(monkeypatch)
        await load_graph("vsa_tech")
        assert chamadas[0]["contexto_chars"] is None
        assert chamadas[0]["trim_keep_turns"] is None
