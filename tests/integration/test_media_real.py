"""Testes de integração real para pré-processamento de mídia.

Valida que o OpenRouter consegue descrever uma imagem e transcrever
um áudio de verdade — sem mocks na IA, apenas no download de mídia.

Executar com: uv run pytest tests/integration/test_media_real.py -v
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.worker.media import (
    _describe_image,
    _transcribe_audio,
    preprocess_incoming_message,
)

ASSETS_DIR = Path(__file__).parent.parent / "assets"


# --- Fixtures ---


@pytest.fixture
def media_api_key(live_openrouter_api_key):
    """Garante opt-in explícito para os testes live de mídia."""
    return live_openrouter_api_key


@pytest.fixture
def image_bytes():
    """Lê tests/assets/sample.png como bytes."""
    path = ASSETS_DIR / "sample.png"
    if not path.exists():
        pytest.skip("tests/assets/sample.png não encontrado")
    return path.read_bytes()


@pytest.fixture
def audio_bytes():
    """Lê tests/assets/sample.ogg como bytes."""
    path = ASSETS_DIR / "sample.ogg"
    if not path.exists():
        pytest.skip("tests/assets/sample.ogg não encontrado")
    return path.read_bytes()


# --- Testes ---


class TestMediaReal:
    """Testes de integração com chamadas reais ao OpenRouter."""

    async def test_describe_image_returns_text(self, media_api_key, image_bytes):
        """Envia imagem real ao OpenRouter e verifica descrição não-vazia."""
        result = await _describe_image(image_bytes, "image/png")

        print(f"\n--- Descrição da imagem ---\n{result}\n---")

        assert isinstance(result, str)
        assert len(result) >= 10, f"Descrição muito curta: '{result}'"

    async def test_transcribe_audio_returns_text(self, media_api_key, audio_bytes):
        """Envia áudio real ao OpenRouter e verifica transcrição não-vazia."""
        result = await _transcribe_audio(audio_bytes, "audio/ogg")

        print(f"\n--- Transcrição do áudio ---\n{result}\n---")

        assert isinstance(result, str)
        assert len(result) >= 10, f"Transcrição muito curta: '{result}'"

    async def test_preprocess_image_end_to_end(self, media_api_key, image_bytes):
        """Fluxo completo de imagem: mocka só o download, IA é real."""
        with patch(
            "whatsapp_langchain.worker.media.download_media",
            new=AsyncMock(return_value=image_bytes),
        ):
            result = await preprocess_incoming_message(
                body="Descreva",
                media_url="http://fake/image.png",
                media_type="image/png",
            )

        print(f"\n--- Texto normalizado (imagem) ---\n{result.normalized_text}\n---")

        assert result.should_invoke_agent is True
        assert result.media_processing_status == "processed"
        assert "[Descrição de imagem]" in (result.normalized_text or "")

    async def test_preprocess_audio_end_to_end(self, media_api_key, audio_bytes):
        """Fluxo completo de áudio: mocka só o download, IA é real."""
        with patch(
            "whatsapp_langchain.worker.media.download_media",
            new=AsyncMock(return_value=audio_bytes),
        ):
            result = await preprocess_incoming_message(
                body="Transcreva",
                media_url="http://fake/audio.ogg",
                media_type="audio/ogg",
            )

        print(f"\n--- Texto normalizado (áudio) ---\n{result.normalized_text}\n---")

        assert result.should_invoke_agent is True
        assert result.media_processing_status == "processed"
        assert "[Transcrição de áudio]" in (result.normalized_text or "")
