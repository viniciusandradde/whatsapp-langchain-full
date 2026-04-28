"""Testes da factory de criação do modelo LLM com rate limiter."""

from langchain_core.rate_limiters import InMemoryRateLimiter

from whatsapp_langchain.shared.llm import create_chat_model


class TestCreateChatModel:
    """Testes da factory create_chat_model."""

    def test_creates_model_with_rate_limiter(self):
        """Modelo retornado deve ter rate_limiter configurado."""
        model = create_chat_model()
        assert model.rate_limiter is not None
        assert isinstance(model.rate_limiter, InMemoryRateLimiter)

    def test_rate_limiter_uses_settings(self):
        """Rate limiter deve refletir valores configurados nos settings."""
        from whatsapp_langchain.shared.config import settings

        model = create_chat_model()
        limiter = model.rate_limiter
        assert isinstance(limiter, InMemoryRateLimiter)
        expected_rps = settings.llm_rate_limit_requests_per_second
        assert limiter.requests_per_second == expected_rps
        assert limiter.max_bucket_size == settings.llm_rate_limit_max_burst

    def test_custom_model_name(self):
        """Deve aceitar override do modelo."""
        model = create_chat_model(model="custom/model-name")
        assert model.model_name == "custom/model-name"

    def test_custom_temperature(self):
        """Deve aceitar override da temperatura."""
        model = create_chat_model(temperature=0.0)
        assert model.temperature == 0.0

    def test_default_model_from_settings(self):
        """Sem override, deve usar modelo dos settings."""
        from whatsapp_langchain.shared.config import settings

        model = create_chat_model()
        assert model.model_name == settings.openrouter_model

    def test_base_url_from_settings(self):
        """Base URL deve vir dos settings."""
        from whatsapp_langchain.shared.config import settings

        model = create_chat_model()
        assert model.openai_api_base == settings.openrouter_base_url

    def test_reuses_limiter_for_same_settings(self):
        """Modelos com mesma config devem compartilhar o mesmo limiter."""
        model_a = create_chat_model(model="m1")
        model_b = create_chat_model(model="m2")
        assert model_a.rate_limiter is model_b.rate_limiter
