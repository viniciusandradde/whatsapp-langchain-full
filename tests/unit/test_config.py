"""Testes das validacoes de configuracao por ambiente."""

import pytest

from whatsapp_langchain.shared.config import (
    MIN_PRODUCTION_SECRET_LENGTH,
    Settings,
)


def test_frontend_origins_parses_csv(monkeypatch):
    monkeypatch.setenv(
        "FRONTEND_ORIGINS", "http://localhost:3000,https://app.rhawk.pro"
    )
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    assert s.frontend_origins_list == ["http://localhost:3000", "https://app.rhawk.pro"]


def test_frontend_origins_default_allows_localhost():
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    assert "http://localhost:3000" in s.frontend_origins_list


class TestRuntimeSettingsValidation:
    """Garantias de configuração mínima e hardening por ambiente."""

    def test_rejects_missing_internal_service_token(self):
        """API deve falhar cedo quando o token interno não está preenchido."""
        settings = Settings(environment="development", internal_service_token="")

        with pytest.raises(ValueError, match="INTERNAL_SERVICE_TOKEN"):
            settings.validate_runtime_settings()

    def test_rejects_short_internal_service_token_in_production(self):
        """Production exige token forte com tamanho minimo."""
        settings = Settings(
            environment="production",
            internal_service_token="curto-demais",
        )

        with pytest.raises(ValueError, match="INTERNAL_SERVICE_TOKEN"):
            settings.validate_runtime_settings()

    def test_accepts_non_empty_token_in_development(self):
        """Desenvolvimento local aceita qualquer token não-vazio."""
        settings = Settings(
            environment="development",
            internal_service_token="token-local",
        )

        settings.validate_runtime_settings()

    def test_accepts_strong_internal_service_token_in_production(self):
        """Production aceita token nao-default com comprimento suficiente."""
        settings = Settings(
            environment="production",
            internal_service_token="x" * MIN_PRODUCTION_SECRET_LENGTH,
            validate_twilio_signature=True,
        )

        settings.validate_runtime_settings()


def test_validate_runtime_fails_when_signature_disabled_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("VALIDATE_TWILIO_SIGNATURE", "false")
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    with pytest.raises(ValueError, match="VALIDATE_TWILIO_SIGNATURE"):
        s.validate_runtime_settings()


def test_validate_runtime_passes_when_signature_enabled_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("VALIDATE_TWILIO_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "abc")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://example.com")
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    s.validate_runtime_settings()  # não deve levantar


def test_validate_runtime_fails_when_frontend_origins_empty_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("VALIDATE_TWILIO_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "abc")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://example.com")
    monkeypatch.setenv("FRONTEND_ORIGINS", "")
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    with pytest.raises(ValueError, match="FRONTEND_ORIGINS"):
        s.validate_runtime_settings()


def test_validate_runtime_passes_when_frontend_origins_set_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("VALIDATE_TWILIO_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "abc")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://example.com")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.rhawk.pro")
    from whatsapp_langchain.shared.config import Settings

    s = Settings()
    s.validate_runtime_settings()  # não deve levantar
