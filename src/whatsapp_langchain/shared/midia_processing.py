"""Funções reusáveis de processamento de mídia (imagem/áudio) via OpenRouter Vision.

Refatorado de `worker/media.py` (Atendimento Completo — 2026-05-07) pra
permitir uso DENTRO do grafo do agente via tools (`agents/tools/midia.py`).

`worker/media.py` continua usando os mesmos helpers — apenas re-importa.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()

_MAX_MEDIA_REDIRECTS = 5


def _host_is_public(host: str) -> bool:
    """True se TODOS os IPs do host são públicos (anti-SSRF).

    Bloqueia loopback, privados, link-local (169.254.x — metadata cloud!),
    reservados, multicast e unspecified. Faz DNS resolve (bloqueante; chamar
    via asyncio.to_thread).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _validate_media_url(url: str) -> str:
    """Valida scheme http(s) + host público. Retorna o host. Levanta ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"scheme de mídia não permitido: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host or not _host_is_public(host):
        raise ValueError(f"host de mídia não permitido (privado/interno): {host!r}")
    return host


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

    Suporta:
    - `data:` URLs (RFC 2397) — decoda base64 inline. Usado pra mídia já
      pre-fetched do Evolution (evita re-baixar URL encrypted WhatsApp).
    - URLs HTTP/HTTPS — GET simples, com cada redirect validado.
    """
    if url.startswith("data:"):
        # data:<mime>[;base64],<payload>
        header, _, payload = url[5:].partition(",")
        is_base64 = ";base64" in header
        mime = header.split(";")[0] or "application/octet-stream"
        if is_base64:
            return base64.b64decode(payload), mime
        # data URL plain (raro) — return as bytes
        from urllib.parse import unquote

        return unquote(payload).encode("utf-8"), mime

    # SSRF guard: segue redirects MANUALMENTE, validando cada hop. Provider de
    # mídia costuma redirecionar pra storage (S3 e afins), então não dá pra
    # desligar redirect — mas cada hop é validado antes de ser seguido.
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
        for _ in range(_MAX_MEDIA_REDIRECTS):
            # Guard de SSRF: valida o hop antes de segui-lo. O retorno (host)
            # era usado só para decidir a auth do provider, que saiu junto com
            # o Twilio — a validação continua obrigatória.
            await asyncio.to_thread(_validate_media_url, current)
            response = await client.get(current)
            if response.is_redirect:
                loc = response.headers.get("location")
                if not loc:
                    response.raise_for_status()
                current = urljoin(current, loc)
                continue
            response.raise_for_status()
            ctype = (
                response.headers.get("content-type", "").split(";")[0].strip() or None
            )
            return response.content, ctype
        raise ValueError("mídia: muitos redirects")


async def download_evolution_media_b64(
    instance: str,
    message_key_id: str,
    remote_jid: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    convert_to_mp4: bool = False,
) -> tuple[str, str] | None:
    """Baixa mídia via Evolution API endpoint `getBase64FromMediaMessage`.

    URLs em `imageMessage.url` são encryptadas WhatsApp (mmg.whatsapp.net) —
    não dá pra baixar direto. Evolution oferece esse endpoint que faz
    decrypt server-side e retorna base64.

    Retorna (base64_str, mimetype) ou None se falhar.
    """
    base = (base_url or settings.evolution_api_url or "").rstrip("/")
    key = api_key or (
        settings.evolution_api_key.get_secret_value()
        if settings.evolution_api_key is not None
        else None
    )
    if not base or not key:
        return None
    url = f"{base}/chat/getBase64FromMediaMessage/{instance}"
    payload: dict = {
        "message": {
            "key": {"id": message_key_id, "remoteJid": remote_jid, "fromMe": False}
        },
        "convertToMp4": convert_to_mp4,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"apikey": key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            j = resp.json()
            b64 = j.get("base64")
            mime = j.get("mimetype") or "application/octet-stream"
            if isinstance(b64, str) and b64:
                return (b64, mime)
            return None
    except Exception as exc:
        # Sem raise: mídia é best-effort (mensagem segue só com texto).
        # Mas o motivo PRECISA aparecer no log — um 401 silencioso aqui
        # custou horas de diagnóstico.
        logger.warning(
            "evolution_media_download_failed",
            instance=instance,
            message_key_id=message_key_id,
            error=str(exc)[:200],
        )
        return None


async def chat_completion_media(messages: list[dict], model: str | None = None) -> str:
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
        # O OpenRouter responde **HTTP 200 com envelope de erro** quando o
        # provedor recusa (capacidade, rate limit, indisponibilidade momentânea).
        # Acessar `["choices"]` direto virava `KeyError: 'choices'`, que chega no
        # log como uma palavra solta e não diz nada — foi o que aconteceu no
        # atendimento 574: o áudio do cliente foi descartado e ninguém soube por
        # quê. O mesmo áudio transcreveu normalmente minutos depois.
        if "choices" not in result:
            erro = result.get("error") or {}
            detalhe = erro.get("message") or str(result)[:200]
            raise RuntimeError(f"OpenRouter recusou a chamada de mídia: {detalhe}")
        content = result["choices"][0]["message"].get("content")
        return _extract_text(content).strip()


async def describe_image_bytes(
    media_bytes: bytes,
    media_type: str,
    model: str | None = None,
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
