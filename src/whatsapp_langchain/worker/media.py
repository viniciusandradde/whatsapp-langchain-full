"""Pré-processamento de mídia (imagem/áudio) antes do agente.

Regra arquitetural:
- O agente sempre recebe texto.
- Se mídia está desabilitada ou falha no pré-processamento, a mensagem não
  chega ao agente e uma resposta automática é enviada ao usuário.
"""

from __future__ import annotations

import base64  # noqa: F401  — preservado caso outros call-sites legacy importem
from dataclasses import dataclass

import httpx
import structlog
from langchain_core.messages import HumanMessage

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.midia_processing import (
    _audio_format_from_media_type,  # re-export pra compat
    _extract_text,  # re-export
    _media_kind,  # re-export
    chat_completion_media as _chat_completion_media,
    describe_image_bytes as _describe_image,
    transcribe_audio_bytes as _transcribe_audio,
)

# Aliases pra preservar compat interna (alguns lugares ainda usam estas refs)
__all__ = [
    "AUTO_RESPONSE_MEDIA_FAILURE",
    "preprocess_incoming_message",
    "build_human_message",
    "download_media",
]

logger = structlog.get_logger()

AUTO_RESPONSE_MEDIA_FAILURE = (
    "Estamos com dificuldades em processar imagens/audio. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_IMAGE_DISABLED = (
    "No momento o processamento de imagens está desativado. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_AUDIO_DISABLED = (
    "No momento o processamento de áudio está desativado. "
    "Por favor, mande mensagem de texto."
)
AUTO_RESPONSE_UNSUPPORTED_MEDIA = (
    "Este tipo de mídia não é suportado no momento. Por favor, mande mensagem de texto."
)


@dataclass
class MediaPreprocessResult:
    """Resultado do pré-processamento de entrada antes do agente."""

    should_invoke_agent: bool
    normalized_text: str | None
    media_processing_status: str
    media_processing_error: str | None = None
    auto_response: str | None = None


async def download_media(url: str) -> bytes:
    """Wrapper compat — delega pro shared.midia_processing.download_media
    que suporta data: URLs (mig 2026-05-07 fix Evolution mídia)."""
    from whatsapp_langchain.shared.midia_processing import (
        download_media as _shared_download,
    )
    body, _ctype = await _shared_download(url)
    return body


# _media_kind, _audio_format_from_media_type, _extract_text,
# _chat_completion_media, _describe_image, _transcribe_audio
# ↑ todos reexportados de shared/midia_processing.py (refator 2026-05-07)


async def preprocess_incoming_message(
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
    midia_model: str | None = None,
) -> MediaPreprocessResult:
    """Normaliza entrada para texto antes da chamada ao agente.

    Args:
        body: Texto recebido (pode ser vazio quando é só mídia).
        media_url: URL Twilio da mídia (None = sem mídia).
        media_type: MIME type da mídia.
        midia_model: Override do modelo multimodal.
                     None = usa settings.openrouter_midia_model.
    """
    if not media_url and not media_type:
        return MediaPreprocessResult(
            should_invoke_agent=True,
            normalized_text=body,
            media_processing_status="none",
        )

    # Payload de mídia incompleto: não invoca agente.
    if not media_url or not media_type:
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="unsupported",
            auto_response=AUTO_RESPONSE_UNSUPPORTED_MEDIA,
        )

    kind = _media_kind(media_type)

    if kind == "image" and not settings.media_image_enabled:
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="disabled",
            auto_response=AUTO_RESPONSE_IMAGE_DISABLED,
        )

    if kind == "audio" and not settings.media_audio_enabled:
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="disabled",
            auto_response=AUTO_RESPONSE_AUDIO_DISABLED,
        )

    if kind == "unsupported":
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="unsupported",
            auto_response=AUTO_RESPONSE_UNSUPPORTED_MEDIA,
        )

    try:
        media_bytes = await download_media(media_url)

        if kind == "image":
            description = await _describe_image(
                media_bytes, media_type, model=midia_model
            )
            parts = [
                p for p in [body.strip(), f"[Descrição de imagem]: {description}"] if p
            ]
            normalized = "\n".join(parts)

        elif kind == "audio":
            transcription = await _transcribe_audio(
                media_bytes, media_type, model=midia_model
            )
            parts = [
                p
                for p in [body.strip(), f"[Transcrição de áudio]: {transcription}"]
                if p
            ]
            normalized = "\n".join(parts)

        else:
            # Guard-rail: só entra aqui em caso inesperado
            return MediaPreprocessResult(
                should_invoke_agent=False,
                normalized_text=None,
                media_processing_status="unsupported",
                auto_response=AUTO_RESPONSE_UNSUPPORTED_MEDIA,
            )

        return MediaPreprocessResult(
            should_invoke_agent=True,
            normalized_text=normalized,
            media_processing_status="processed",
        )

    except Exception as e:
        logger.error(
            "media_preprocessing_failed",
            media_type=media_type,
            error=str(e),
        )
        return MediaPreprocessResult(
            should_invoke_agent=False,
            normalized_text=None,
            media_processing_status="failed",
            media_processing_error=str(e),
            auto_response=AUTO_RESPONSE_MEDIA_FAILURE,
        )


async def build_human_message(
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
) -> HumanMessage:
    """Compatibilidade: retorna HumanMessage de texto (sem multimodal)."""
    pre = await preprocess_incoming_message(
        body=body,
        media_url=media_url,
        media_type=media_type,
    )
    text = pre.normalized_text or body or pre.auto_response or ""
    return HumanMessage(content=text)
