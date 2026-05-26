"""Smoke tests pro shared/langfuse_client.

Cobre os 3 cenários críticos do contrato:
  1. Feature off (sem keys) → todas funções são no-op silencioso.
  2. get_system_prompt cai no fallback quando client retorna None.
  3. post_score não levanta mesmo com trace_id None ou client None.

Sem DB, sem container Langfuse — só importa o módulo e bate nas funções.
"""

from __future__ import annotations

from whatsapp_langchain.shared import langfuse_client


class TestLangfuseDisabled:
    """Sem LANGFUSE_PUBLIC_KEY/SECRET_KEY no env, tudo é no-op."""

    def setup_method(self) -> None:
        # Reset singleton entre testes
        langfuse_client._CLIENT = None
        langfuse_client._CLIENT_INIT_FAILED = False

    def test_get_client_returns_none_when_disabled(self) -> None:
        from whatsapp_langchain.shared.config import settings

        # settings default tem langfuse_public_key=None → enabled=False
        if settings.langfuse_enabled:
            return  # ambiente já tem keys; teste não aplica
        assert langfuse_client.get_client() is None

    def test_create_trace_id_returns_none_when_disabled(self) -> None:
        from whatsapp_langchain.shared.config import settings

        if settings.langfuse_enabled:
            return
        assert langfuse_client.create_trace_id(seed="msg:1") is None

    def test_get_callback_handler_returns_none_when_disabled(self) -> None:
        from whatsapp_langchain.shared.config import settings

        if settings.langfuse_enabled:
            return
        assert langfuse_client.get_callback_handler(trace_id="any") is None

    def test_post_score_silent_noop_when_disabled(self) -> None:
        # Não deve levantar nem com trace_id válido — client é None.
        langfuse_client.post_score(
            trace_id="trace-fake",
            name="nps",
            value=9.0,
            comment="bom",
        )

    def test_post_score_silent_noop_with_none_trace_id(self) -> None:
        langfuse_client.post_score(
            trace_id=None,
            name="nps",
            value=9.0,
        )

    def test_flush_silent_noop_when_disabled(self) -> None:
        langfuse_client.flush()


class TestSystemPromptFallback:
    """get_system_prompt cai no fallback file-based quando Langfuse off."""

    def setup_method(self) -> None:
        langfuse_client._CLIENT = None
        langfuse_client._CLIENT_INIT_FAILED = False

    def test_fallback_returned_when_disabled(self) -> None:
        from whatsapp_langchain.shared.config import settings

        if settings.langfuse_enabled:
            return

        fallback = "Você é um assistente útil pt-BR."
        text, meta = langfuse_client.get_system_prompt(
            name="system-prompt:test_agent",
            fallback=fallback,
        )
        assert text == fallback
        assert meta is None


class TestSingleton:
    """get_client retorna mesma instância em chamadas sucessivas."""

    def setup_method(self) -> None:
        langfuse_client._CLIENT = None
        langfuse_client._CLIENT_INIT_FAILED = False

    def test_get_client_idempotent_when_disabled(self) -> None:
        # Off → ambas chamadas retornam None (singleton "vazio" também).
        first = langfuse_client.get_client()
        second = langfuse_client.get_client()
        assert first is second  # ambos None
