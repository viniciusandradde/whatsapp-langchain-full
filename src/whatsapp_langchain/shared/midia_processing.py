"""Funções reusáveis de processamento de mídia (imagem/áudio) via OpenRouter Vision.

Refatorado de `worker/media.py` (Atendimento Completo — 2026-05-07) pra
permitir uso DENTRO do grafo do agente via tools (`agents/tools/midia.py`).

`worker/media.py` continua usando os mesmos helpers — apenas re-importa.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from whatsapp_langchain.shared.config import settings


def _audio_format_from_media_type(media_type: str) -> str:
    """Mapeia MIME type → formato aceito em `input_audio` do OpenRouter."""
    m = (media_type or "").lower()
    if "wav" in m or "wave" in m:
        return "wav"
    if "mpeg" in m or "mp3" in m:
        return "mp3"
    if "ogg" in m:
        return "ogg"
    if "webm" in m:
        return "webm"
    return "ogg"


def _extract_text(content: Any) -> str:
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


def _media_kind(media_type: str | None) -> str:
    if not media_type:
        return "none"
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    if (
        media_type.startswith("application/pdf")
        or media_type.startswith("application/vnd.openxmlformats")
        or media_type.startswith("application/msword")
        or media_type.startswith("text/")
    ):
        return "document"
    return "unsupported"


async def download_media(url: str) -> tuple[bytes, str | None]:
    """Faz download de mídia. Retorna (bytes, content_type detectado).

    Autentica via Twilio API key se configurada (URLs Twilio são protegidas).
    Outras URLs (Evolution / WABA / publicas) seguem sem auth.
    """
    auth = (
        (settings.twilio_api_key_sid, settings.twilio_api_key_secret)
        if settings.twilio_api_key_sid
        else None
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url, auth=auth, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        ctype = response.headers.get("content-type", "").split(";")[0].strip() or None
        return response.content, ctype


async def chat_completion_media(
    messages: list[dict], model: str | None = None
) -> str:
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
                "model": model or settings.openrouter_midia_model,
                "messages": messages,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"].get("content")
        return _extract_text(content).strip()


async def describe_image_bytes(
    media_bytes: bytes, media_type: str, model: str | None = None,
    focus: str | None = None,
) -> str:
    """Descreve imagem (ou responde pergunta direcionada via `focus`).

    Sem `focus`: descrição seca em 1-3 frases.
    Com `focus`: responde pergunta específica olhando a imagem.
    """
    image_b64 = base64.b64encode(media_bytes).decode("utf-8")
    if focus:
        sys_msg = (
            "Você é um analista visual técnico. Responda APENAS o que foi "
            "perguntado, em português brasileiro, sem preâmbulo nem markdown."
        )
        user_text = f"Olhando esta imagem, responda: {focus}"
    else:
        sys_msg = (
            "Você é um extrator técnico de conteúdo visual. "
            "Retorne somente a descrição solicitada, sem saudações, "
            "sem confirmação, sem emojis, sem markdown e sem prefixos."
        )
        user_text = (
            "Descreva esta imagem em português brasileiro, "
            "de forma seca e objetiva (1 a 3 frases). "
            "Não inclua frases como 'descrição recebida', 'aqui está' "
            "ou qualquer preâmbulo."
        )
    return await chat_completion_media(
        [
            {"role": "system", "content": sys_msg},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                ],
            },
        ],
        model=model,
    )


async def transcribe_audio_bytes(
    media_bytes: bytes, media_type: str, model: str | None = None
) -> str:
    """Transcreve áudio literalmente em pt-BR."""
    audio_b64 = base64.b64encode(media_bytes).decode("utf-8")
    audio_format = _audio_format_from_media_type(media_type)
    return await chat_completion_media(
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
                            "do conteúdo."
                        ),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": audio_format},
                    },
                ],
            },
        ],
        model=model,
    )


# ---- Wrappers por URL (usados pelas tools do agente) ----


async def describe_image_url(url: str, focus: str | None = None) -> str:
    """Baixa imagem do URL e analisa. Auto-detecta MIME type."""
    body, ctype = await download_media(url)
    return await describe_image_bytes(body, ctype or "image/jpeg", focus=focus)


async def transcribe_audio_url(url: str) -> str:
    """Baixa áudio do URL e transcreve. Auto-detecta MIME type."""
    body, ctype = await download_media(url)
    return await transcribe_audio_bytes(body, ctype or "audio/ogg")
