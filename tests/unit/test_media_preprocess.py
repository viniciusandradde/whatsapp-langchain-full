"""Testes unitários do pré-processamento de mídia antes do agente."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.worker.media import (
    AUTO_RESPONSE_AUDIO_DISABLED,
    AUTO_RESPONSE_IMAGE_DISABLED,
    AUTO_RESPONSE_MEDIA_FAILURE,
    AUTO_RESPONSE_UNSUPPORTED_MEDIA,
    preprocess_incoming_message,
)


class TestMediaPreprocess:
    """Cenários de normalização de entrada para texto."""

    async def test_no_media_keeps_text(self):
        result = await preprocess_incoming_message(
            body="Olá",
            media_url=None,
            media_type=None,
        )
        assert result.should_invoke_agent is True
        assert result.normalized_text == "Olá"
        assert result.media_processing_status == "none"

    async def test_image_disabled_short_circuits(self):
        with patch.object(settings, "media_image_enabled", False):
            result = await preprocess_incoming_message(
                body="Veja",
                media_url="https://example.com/i.png",
                media_type="image/png",
            )
        assert result.should_invoke_agent is False
        assert result.auto_response == AUTO_RESPONSE_IMAGE_DISABLED
        assert result.media_processing_status == "disabled"

    async def test_audio_disabled_short_circuits(self):
        with patch.object(settings, "media_audio_enabled", False):
            result = await preprocess_incoming_message(
                body="Ouça",
                media_url="https://example.com/a.ogg",
                media_type="audio/ogg",
            )
        assert result.should_invoke_agent is False
        assert result.auto_response == AUTO_RESPONSE_AUDIO_DISABLED
        assert result.media_processing_status == "disabled"

    async def test_unsupported_media_short_circuits(self):
        # video/* não é imagem/áudio/documento → kind "unsupported".
        # (PDF/DOCX agora são "document" suportado, não caem mais aqui.)
        result = await preprocess_incoming_message(
            body="arquivo",
            media_url="https://example.com/clip.mp4",
            media_type="video/mp4",
        )
        assert result.should_invoke_agent is False
        assert result.auto_response == AUTO_RESPONSE_UNSUPPORTED_MEDIA
        assert result.media_processing_status == "unsupported"

    async def test_incomplete_media_payload_short_circuits(self):
        result = await preprocess_incoming_message(
            body="arquivo",
            media_url="https://example.com/file.ogg",
            media_type=None,
        )
        assert result.should_invoke_agent is False
        assert result.auto_response == AUTO_RESPONSE_UNSUPPORTED_MEDIA
        assert result.media_processing_status == "unsupported"

    async def test_image_processed_to_text(self):
        with (
            patch.object(settings, "media_image_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(return_value=b"img-bytes"),
            ),
            patch(
                "whatsapp_langchain.worker.media._describe_image",
                new=AsyncMock(return_value="um diagrama de arquitetura"),
            ),
        ):
            result = await preprocess_incoming_message(
                body="Descreva",
                media_url="https://example.com/i.png",
                media_type="image/png",
            )

        assert result.should_invoke_agent is True
        assert result.media_processing_status == "processed"
        assert "[Descrição de imagem]: um diagrama de arquitetura" in (
            result.normalized_text or ""
        )

    async def test_audio_preprocess_failure_returns_auto_response(self):
        with (
            patch.object(settings, "media_audio_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            result = await preprocess_incoming_message(
                body="Transcreva",
                media_url="https://example.com/a.ogg",
                media_type="audio/ogg",
            )

        assert result.should_invoke_agent is False
        assert result.media_processing_status == "failed"
        assert result.auto_response == AUTO_RESPONSE_MEDIA_FAILURE
        assert "network error" in (result.media_processing_error or "")


class TestEnvelopeDeErroDoOpenRouter:
    """HTTP 200 sem `choices` não pode virar `KeyError: 'choices'`.

    O OpenRouter responde 200 com envelope de erro quando o provedor recusa
    (capacidade, rate limit, indisponibilidade). O código acessava
    `result["choices"]` direto, e o log recebia a palavra `'choices'` — que não
    diz nada a quem investiga. Aconteceu no atendimento 574: o áudio do cliente
    foi descartado e o mesmo arquivo transcreveu normalmente minutos depois.
    """

    async def test_erro_com_200_vira_mensagem_legivel(self):
        import httpx

        from whatsapp_langchain.shared import midia_processing as mp

        class _FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"error": {"message": "Provider returned error", "code": 429}}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return _FakeResp()

        with (
            patch.object(httpx, "AsyncClient", lambda *a, **kw: _FakeClient()),
            patch.object(
                mp.settings, "openrouter_api_key", SecretStr("sk-or-v1-teste")
            ),
        ):
            with pytest.raises(RuntimeError) as exc:
                await mp.chat_completion_media([{"role": "user", "content": "oi"}])

        # A mensagem tem que carregar a razão, não a chave que faltou.
        assert "Provider returned error" in str(exc.value)
        assert "choices" not in str(exc.value)
