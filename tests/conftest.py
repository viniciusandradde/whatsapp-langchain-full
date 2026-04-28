"""Fixtures compartilhadas para testes.

Este arquivo é carregado automaticamente pelo pytest.
Contém fixtures reutilizáveis em todos os testes.
"""

import os

import pytest
from dotenv import load_dotenv

# Carrega .env antes de qualquer teste
load_dotenv()

_PLACEHOLDER_OPENROUTER_KEYS = {
    "",
    "xxx",
    "sk-or-v1-xxx",
}


def _has_valid_live_openrouter_key() -> bool:
    """Retorna True apenas quando os testes live estão explicitamente habilitados."""
    enabled = os.getenv("OPENROUTER_LIVE_TESTS", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return api_key not in _PLACEHOLDER_OPENROUTER_KEYS


@pytest.fixture
def live_openrouter_api_key():
    """Exige uma API key real e opt-in explícito para testes live."""
    if not _has_valid_live_openrouter_key():
        pytest.skip(
            "Teste live requer OPENROUTER_API_KEY valido e OPENROUTER_LIVE_TESTS=1"
        )

    return os.environ["OPENROUTER_API_KEY"]


def _twilio_smoke_enabled() -> tuple[bool, str | None]:
    """Retorna (enabled, número de destino) se opt-in válido."""
    flag = os.getenv("TWILIO_LIVE_TESTS", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False, None
    number = os.getenv("TWILIO_TEST_TO_NUMBER", "").strip()
    if not number or not number.startswith("+") or len(number) < 8:
        return False, None
    return True, number


@pytest.fixture
def twilio_live_to_number():
    """Exige TWILIO_LIVE_TESTS=1 e TWILIO_TEST_TO_NUMBER='+...'."""
    enabled, number = _twilio_smoke_enabled()
    if not enabled:
        pytest.skip(
            "Smoke test Twilio requer TWILIO_LIVE_TESTS=1 e "
            "TWILIO_TEST_TO_NUMBER='+<E.164>' (ex: '+5511999999999')"
        )
    # narrowing: _twilio_smoke_enabled garante number não-None quando enabled=True
    assert number is not None
    return number


@pytest.fixture
def sample_messages():
    """Mensagens de exemplo para testes de contexto."""
    return [
        {"role": "user", "content": "Olá, meu nome é João."},
        {"role": "assistant", "content": "Olá João! Como posso ajudar?"},
        {"role": "user", "content": "Gosto de programação Python."},
        {"role": "assistant", "content": "Python é ótimo! O que desenvolve?"},
        {"role": "user", "content": "Estou aprendendo sobre LangChain."},
        {"role": "assistant", "content": "LangChain é excelente para agentes."},
        {"role": "user", "content": "Qual a diferença entre trim e summarize?"},
    ]
