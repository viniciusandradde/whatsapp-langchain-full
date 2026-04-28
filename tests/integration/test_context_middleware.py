"""Testes de integração para middlewares de contexto.

Os cenários com chamadas reais ao modelo são opt-in e exigem:
- OPENROUTER_API_KEY válida
- OPENROUTER_LIVE_TESTS=1

Executar com: pytest tests/integration/ -v
"""

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from whatsapp_langchain.agents.middleware import get_context_middleware

# --- Fixtures ---


@pytest.fixture
def model(live_openrouter_api_key):
    """Modelo configurado para testes."""
    return ChatOpenAI(
        model="openai/gpt-oss-120b",
        api_key=SecretStr(live_openrouter_api_key),
        base_url="https://openrouter.ai/api/v1",
    )


# --- Testes do Trim Middleware ---


class TestTrimMiddleware:
    """Testes para a estratégia trim (por turnos)."""

    def test_trim_creates_middleware(self):
        """Verifica que o trim cria o middleware corretamente."""
        middleware = get_context_middleware(strategy="trim", trim_keep_turns=2)

        assert len(middleware) == 1
        assert middleware[0] is not None

    def test_trim_removes_old_turns(self):
        """Invoca o middleware real e verifica remoção de turnos antigos."""
        from langgraph.graph import add_messages

        from whatsapp_langchain.agents.middleware.trim import create_trim_middleware

        # keep_turns=2 → mantém os últimos 2 turnos
        mw = create_trim_middleware(keep_turns=2)

        # 4 turnos: [h1 a1] [h2 a2] [h3 a3] [h4]
        messages = [
            HumanMessage(content="Olá", id="h1"),
            AIMessage(content="Resp 1", id="a1"),
            HumanMessage(content="Msg 2", id="h2"),
            AIMessage(content="Resp 2", id="a2"),
            HumanMessage(content="Msg 3", id="h3"),
            AIMessage(content="Resp 3", id="a3"),
            HumanMessage(content="Msg 4", id="h4"),
        ]

        result = mw.before_model({"messages": messages}, None)

        # Deve remover turnos 1 e 2 (h1, a1, h2, a2 = 4 mensagens)
        assert result is not None
        assert len(result["messages"]) == 4

        # Aplica pelo reducer real — igual ao que o LangGraph faz
        final = add_messages(messages, result["messages"])

        assert len(final) == 3
        assert final[0].content == "Msg 3"
        assert final[1].content == "Resp 3"
        assert final[2].content == "Msg 4"

    def test_trim_with_tool_calls(self):
        """Turno com tool_calls (4+ msgs) conta como 1 turno."""
        from langgraph.graph import add_messages

        from whatsapp_langchain.agents.middleware.trim import create_trim_middleware

        # keep_turns=2 → mantém os últimos 2 turnos
        mw = create_trim_middleware(keep_turns=2)

        # Turno 1: simples (h1, a1)
        # Turno 2: com tool_calls (h2, a2_tool_call, tool_result, a2_final)
        # Turno 3: simples (h3, a3)
        messages = [
            HumanMessage(content="Olá", id="h1"),
            AIMessage(content="Resp 1", id="a1"),
            HumanMessage(content="Consulta estoque", id="h2"),
            AIMessage(
                content="",
                id="a2_call",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "tc1",
                            "function": {
                                "name": "check",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
            ),
            ToolMessage(content="42 unidades", id="t1", tool_call_id="tc1"),
            AIMessage(content="Temos 42 unidades!", id="a2_final"),
            HumanMessage(content="Obrigado", id="h3"),
            AIMessage(content="De nada!", id="a3"),
        ]

        result = mw.before_model({"messages": messages}, None)

        # Deve remover turno 1 (h1, a1 = 2 mensagens)
        assert result is not None
        assert len(result["messages"]) == 2

        # Aplica pelo reducer real
        final = add_messages(messages, result["messages"])

        # Restam turnos 2 e 3 (6 mensagens)
        assert len(final) == 6
        assert final[0].content == "Consulta estoque"  # h2
        assert final[1].id == "a2_call"
        assert final[2].content == "42 unidades"  # tool result
        assert final[3].content == "Temos 42 unidades!"  # a2_final
        assert final[4].content == "Obrigado"  # h3
        assert final[5].content == "De nada!"  # a3

    def test_trim_no_op_when_few_turns(self):
        """Não faz nada quando há turnos suficientes (dentro do limite)."""
        from whatsapp_langchain.agents.middleware.trim import create_trim_middleware

        mw = create_trim_middleware(keep_turns=3)

        # Apenas 2 turnos — abaixo do limite de 3
        messages = [
            HumanMessage(content="Olá", id="h1"),
            AIMessage(content="Resp 1", id="a1"),
            HumanMessage(content="Tudo bem?", id="h2"),
            AIMessage(content="Tudo sim!", id="a2"),
        ]

        result = mw.before_model({"messages": messages}, None)

        assert result is None

    def test_trim_exact_boundary(self):
        """Não faz nada quando o número de turnos é exatamente o limite."""
        from whatsapp_langchain.agents.middleware.trim import create_trim_middleware

        mw = create_trim_middleware(keep_turns=2)

        # Exatamente 2 turnos = limite
        messages = [
            HumanMessage(content="Olá", id="h1"),
            AIMessage(content="Resp 1", id="a1"),
            HumanMessage(content="Msg 2", id="h2"),
            AIMessage(content="Resp 2", id="a2"),
        ]

        result = mw.before_model({"messages": messages}, None)

        assert result is None

    def test_trim_with_agent_integration(self, model):
        """Teste de integração: agente com trim responde corretamente."""
        middleware = get_context_middleware(strategy="trim", trim_keep_turns=2)

        agent = create_agent(
            model=model,
            tools=[],
            system_prompt="Responda de forma breve.",
            middleware=middleware,
        )

        # Primeira mensagem
        result = agent.invoke(
            {"messages": [HumanMessage(content="Olá, meu nome é Carlos.")]},
            config={"configurable": {"thread_id": "test-trim-1"}},
        )

        assert result is not None
        assert "messages" in result


# --- Testes do Summarize Middleware ---


class TestSummarizeMiddleware:
    """Testes para a estratégia summarize."""

    def test_summarize_creates_middleware(self):
        """Verifica que o summarize cria o middleware corretamente."""
        middleware = get_context_middleware(
            strategy="summarize",
            summarize_trigger_tokens=100,
            summarize_keep_messages=2,
        )

        assert len(middleware) == 1
        assert middleware[0] is not None

    def test_summarize_no_op_below_threshold(self):
        """Não sumariza quando tokens estão abaixo do threshold."""
        from whatsapp_langchain.agents.middleware.summarize import (
            create_summarize_middleware,
        )

        # trigger_tokens alto → poucas mensagens não acionam
        mw = create_summarize_middleware(
            trigger_tokens=10000,
            keep_messages=2,
        )

        messages = [
            HumanMessage(content="Olá", id="h1"),
            AIMessage(content="Oi!", id="a1"),
            HumanMessage(content="Tudo bem?", id="h2"),
            AIMessage(content="Tudo sim!", id="a2"),
        ]

        result = mw.before_model({"messages": messages}, None)

        # Nenhuma sumarização necessária
        assert result is None

    def test_summarize_triggers_on_threshold(self, model):
        """Sumariza quando tokens excedem o threshold."""
        from whatsapp_langchain.agents.middleware.summarize import (
            create_summarize_middleware,
        )

        # trigger_tokens baixo → sumariza com poucas mensagens
        # Contagem aproximada: ~4 chars/token
        mw = create_summarize_middleware(
            model=model,
            trigger_tokens=50,
            keep_messages=2,
        )

        # Mensagens com texto suficiente para ultrapassar 50 tokens
        messages = [
            HumanMessage(
                content="Meu nome é Carlos, moro em São Paulo.",
                id="h1",
            ),
            AIMessage(
                content="Prazer Carlos! São Paulo é incrível.",
                id="a1",
            ),
            HumanMessage(
                content="Trabalho com LangGraph e WhatsApp.",
                id="h2",
            ),
            AIMessage(
                content="LangGraph é ótimo para agentes.",
                id="a2",
            ),
            HumanMessage(
                content="Preciso de ajuda com middleware.",
                id="h3",
            ),
            AIMessage(
                content="Posso ajudar com trim ou summarize.",
                id="a3",
            ),
        ]

        result = mw.before_model({"messages": messages}, None)

        # Sumarização deve ter sido acionada
        assert result is not None
        assert "messages" in result

        # O SummarizationMiddleware adiciona HumanMessage
        # com lc_source="summarization" contendo o resumo
        summary_msgs = [
            m
            for m in result["messages"]
            if hasattr(m, "additional_kwargs")
            and m.additional_kwargs.get("lc_source") == "summarization"
        ]
        assert len(summary_msgs) == 1
        assert len(summary_msgs[0].content) > 0

    def test_summarize_multi_turn_bounded_history(self, model):
        """Múltiplos turnos com summarize mantém histórico limitado."""
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        middleware = get_context_middleware(
            strategy="summarize",
            summarize_trigger_tokens=100,
            summarize_keep_messages=4,
        )

        agent = create_agent(
            model=model,
            tools=[],
            system_prompt="Responda em uma frase curta.",
            middleware=middleware,
            checkpointer=checkpointer,
        )

        thread = "test-summarize-bounded"
        config = {"configurable": {"thread_id": thread}}

        # Envia 5 mensagens no mesmo thread para acumular tokens
        prompts = [
            "Meu nome é Carlos, moro em São Paulo.",
            "Trabalho como desenvolvedor Python há 5 anos.",
            "Estou estudando LangGraph para chatbots.",
            "Quero integrar com WhatsApp usando Twilio.",
            "Preciso configurar middleware de contexto.",
        ]

        result = None
        for msg in prompts:
            result = agent.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=config,
            )

        # Sem summarize: 10 mensagens (5 human + 5 AI)
        # Com summarize (trigger=100, keep=4): deve ser menor
        final_messages = result["messages"]
        assert len(final_messages) < 10

    def test_summarize_with_agent_integration(self, model):
        """Teste de integração: agente com summarize responde."""
        middleware = get_context_middleware(
            strategy="summarize",
            summarize_trigger_tokens=500,
            summarize_keep_messages=2,
        )

        agent = create_agent(
            model=model,
            tools=[],
            system_prompt="Responda de forma breve.",
            middleware=middleware,
        )

        result = agent.invoke(
            {"messages": [HumanMessage(content="Olá!")]},
            config={"configurable": {"thread_id": "test-sum-1"}},
        )

        assert result is not None
        assert "messages" in result


# --- Testes do None (sem middleware) ---


class TestNoneMiddleware:
    """Testes para strategy=none (sem gerenciamento de contexto)."""

    def test_none_returns_empty_list(self):
        """Verifica que strategy=none retorna lista vazia."""
        middleware = get_context_middleware(strategy="none")

        assert middleware == []
        assert len(middleware) == 0

    def test_none_with_agent_integration(self, model):
        """Teste de integração: agente sem middleware responde corretamente."""
        middleware = get_context_middleware(strategy="none")

        agent = create_agent(
            model=model,
            tools=[],
            system_prompt="Responda de forma breve.",
            middleware=middleware,
        )

        result = agent.invoke(
            {"messages": [HumanMessage(content="Olá!")]},
            config={"configurable": {"thread_id": "test-none-1"}},
        )

        assert result is not None
        assert "messages" in result


# --- Testes da Factory ---


class TestGetContextMiddleware:
    """Testes para a factory get_context_middleware()."""

    def test_default_strategy_comes_from_settings(self):
        """Sem override, a strategy deve vir de shared.config.settings."""
        from unittest.mock import patch

        from whatsapp_langchain.shared.config import settings

        with patch.object(settings, "context_strategy", "summarize"):
            middleware = get_context_middleware()
            assert len(middleware) == 1

    def test_override_parameters(self):
        """Verifica que parâmetros override funcionam."""
        middleware = get_context_middleware(
            strategy="trim",
            trim_keep_turns=3,
        )

        assert len(middleware) == 1

    def test_invalid_strategy_returns_empty(self):
        """Verifica que estratégia inválida retorna lista vazia."""
        middleware = get_context_middleware(strategy="invalid_strategy")

        assert middleware == []

    def test_none_returns_empty(self):
        """Sem estratégia de contexto, não deve haver middlewares."""
        middleware = get_context_middleware(strategy="none")
        assert middleware == []

    def test_trim_returns_one_middleware(self):
        """Trim deve produzir um único middleware."""
        middleware = get_context_middleware(strategy="trim")
        assert len(middleware) == 1
