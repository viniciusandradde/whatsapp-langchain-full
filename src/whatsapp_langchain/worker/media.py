"""Pré-processamento de mídia (imagem/áudio) antes do agente.

Regra arquitetural:
- O agente sempre recebe texto.
- Se mídia está desabilitada ou falha no pré-processamento, a mensagem não
  chega ao agente e uma resposta automática é enviada ao usuário.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx
import structlog
from langchain_core.messages import HumanMessage

from whatsapp_langchain.shared.config import settings

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


async def download_media(
    url: str,
) -> bytes:
    """Faz download de mídia do Twilio.

    Autentica com API Key (api_key_sid:api_key_secret) — mesmas credenciais
    usadas pelo TwilioClient para envio outbound.
    """
    auth = (
        (settings.twilio_api_key_sid, settings.twilio_api_key_secret)
        if settings.twilio_api_key_sid
        else None
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=auth, follow_redirects=True)
        response.raise_for_status()
        return response.content


def _media_kind(media_type: str | None) -> str:
    if not media_type:
        return "none"
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    return "unsupported"


def _audio_format_from_media_type(media_type: str) -> str:
    """Mapeia MIME type para formato aceito em input_audio."""
    m = media_type.lower()
    if "wav" in m or "wave" in m:
        return "wav"
    if "mpeg" in m or "mp3" in m:
        return "mp3"
    if "ogg" in m:
        return "ogg"
    if "webm" in m:
        return "webm"
    return "ogg"


def _extract_text(content: str | list | None) -> str:
    """Extrai texto de respostas OpenRouter com content string ou lista."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
        return "\n".join(t for t in texts if t)
    return str(content)


async def _chat_completion_media(messages: list[dict]) -> str:
    """Executa chamada multimodal no OpenRouter usando modelo de mídia."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openrouter_midia_model,
                "messages": messages,
            },
            timeout=45.0,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"].get("content")
        return _extract_text(content).strip()


async def _describe_image(media_bytes: bytes, media_type: str) -> str:
    image_b64 = base64.b64encode(media_bytes).decode("utf-8")

    return await _chat_completion_media(
        [
            {
                "role": "system",
                "content": (
                    "Você é um extrator técnico de conteúdo visual. "
                    "Retorne somente a descrição solicitada, sem saudações, "
                    "sem confirmação, sem emojis, sem markdown e sem prefixos."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Descreva esta imagem em português brasileiro, "
                            "de forma seca e objetiva (1 a 3 frases). "
                            "Não inclua frases como 'descrição recebida', "
                            "'aqui está' ou qualquer preâmbulo."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                        },
                    },
                ],
            },
        ]
    )


async def _transcribe_audio(media_bytes: bytes, media_type: str) -> str:
    audio_b64 = base64.b64encode(media_bytes).decode("utf-8")
    audio_format = _audio_format_from_media_type(media_type)

    return await _chat_completion_media(
        [
            {
                "role": "system",
                "content": (
                    "Você é um transcritor técnico. "
                    "Retorne somente a transcrição literal do áudio, "
                    "sem saudações, sem confirmação, sem comentários, "
                    "sem emojis e sem prefixos."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcreva este áudio fielmente em português brasileiro. "
                            "A saída deve conter apenas a transcrição crua "
                            "do conteúdo. "
                            "Não inclua frases como "
                            "'Transcrição recebida e confirmada', "
                            "'Segue a transcrição' ou equivalentes."
                        ),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": audio_format,
                        },
                    },
                ],
            },
        ]
    )


async def preprocess_incoming_message(
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
) -> MediaPreprocessResult:
    """Normaliza entrada para texto antes da chamada ao agente."""
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
            description = await _describe_image(media_bytes, media_type)
            parts = [
                p for p in [body.strip(), f"[Descrição de imagem]: {description}"] if p
            ]
            normalized = "\n".join(parts)

        elif kind == "audio":
            transcription = await _transcribe_audio(media_bytes, media_type)
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
