"""Testes das validacoes de configuracao por ambiente."""

import pytest

from whatsapp_langchain.shared.config import (
    MIN_PRODUCTION_SECRET_LENGTH,
    Settings,
)


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
        )

        settings.validate_runtime_settings()
