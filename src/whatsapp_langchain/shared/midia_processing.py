"""Funções reusáveis de processamento de mídia (imagem/áudio) via OpenRouter Vision.

Refatorado de `worker/media.py` (Atendimento Completo — 2026-05-07) pra
permitir uso DENTRO do grafo do agente via tools (`agents/tools/midia.py`).

`worker/media.py` continua usando os mesmos helpers — apenas re-importa.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import httpx
import structlog

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.governanca_ia import (
    CUSTO_FONTE_OPENROUTER,
    CUSTO_FONTE_TABELA,
    acrescentar_consumo,
    calc_custo,
    get_custo_modelo,
    registrar_execucao,
)
from whatsapp_langchain.shared.llm import provider_preferences
from whatsapp_langchain.shared.ssrf_guard import host_is_public, validar_url_externa

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

_MAX_MEDIA_REDIRECTS = 5


# Guarda anti-SSRF unificada em shared/ssrf_guard (reusada por hooks/menu/MCP).
# Aliases preservam os nomes internos deste módulo (e imports existentes).
_host_is_public = host_is_public
_validate_media_url = validar_url_externa


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
    - URLs HTTP/HTTPS — GET simples, sem credencial anexada.
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

    # SSRF guard: segue redirects MANUALMENTE, validando cada hop — a URL de
    # mídia do provider costuma redirecionar pra um storage, então não dá pra
    # desligar redirect; o que dá é validar o destino de cada salto.
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
        for _ in range(_MAX_MEDIA_REDIRECTS):
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


async def registrar_custo_midia(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    modelo: str,
    usage: dict | None,
    generation_id: str | None = None,
    duracao_ms: int | None = None,
    finalidade: str = "midia",
) -> None:
    """Registra em `ia_execucao`/`ia_budget` o custo de UMA chamada multimodal.

    Transcrição de áudio, descrição de imagem e OCR sempre foram POSTs crus ao
    OpenRouter: o gasto não aparecia em `ia_execucao` nem somava no teto mensal
    `ia_budget` (mig 161) — só o caminho do agente, instrumentado pelo
    `llm_callback`, era medido. Uma empresa em modo manual com
    `transcrever_audio_sempre` ligado gastava todo mês sem que o teto visse um
    centavo. Este helper fecha o buraco seguindo o MESMO padrão do callback:
    `usage.cost` da OpenRouter é a verdade (mig 139); a tabela `modelo_llm`
    fica de fallback, marcada como estimativa via `custo_fonte`.

    Best-effort por contrato (mig 164): falha aqui loga warning e NUNCA
    derruba o processamento da mídia.
    """
    try:
        usage = usage or {}
        tokens_input = usage.get("prompt_tokens", 0) or 0
        tokens_output = usage.get("completion_tokens", 0) or 0
        tokens_cached = (usage.get("prompt_tokens_details") or {}).get(
            "cached_tokens", 0
        ) or 0

        # Convenção OpenRouter "provedor/nome" — mesmo split do llm_callback.
        if "/" in modelo:
            provedor, nome = modelo.split("/", 1)
        else:
            provedor, nome = "?", modelo

        custo_openrouter = usage.get("cost")
        custo_total: float | None
        if custo_openrouter is not None and custo_openrouter > 0:
            custo_total = float(custo_openrouter)
            custo_fonte = CUSTO_FONTE_OPENROUTER
        else:
            custo_in, custo_out, custo_cache = await get_custo_modelo(
                pool, empresa_id, provedor, nome
            )
            custo_total = calc_custo(
                tokens_input,
                tokens_output,
                custo_in,
                custo_out,
                tokens_cached=tokens_cached,
                custo_cache_mtok=custo_cache,
            )
            custo_fonte = CUSTO_FONTE_TABELA if custo_total is not None else None

        await registrar_execucao(
            pool,
            empresa_id=empresa_id,
            modelo_provedor=provedor,
            modelo_nome=nome,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cached=tokens_cached,
            custo_total=custo_total,
            duracao_ms=duracao_ms,
            status="success",
            metadata={"finalidade": finalidade},
            custo_fonte=custo_fonte,
            openrouter_generation_id=generation_id,
        )
        if custo_total is not None and custo_total > 0:
            await acrescentar_consumo(pool, empresa_id, custo_total)
    except Exception as exc:
        logger.warning(
            "custo_midia_registro_falhou",
            empresa_id=empresa_id,
            modelo=modelo,
            finalidade=finalidade,
            error=str(exc)[:200],
        )


async def chat_completion_media(
    messages: list[dict],
    model: str | None = None,
    *,
    pool: AsyncConnectionPool | None = None,
    empresa_id: int | None = None,
    finalidade: str = "midia",
) -> str:
    """Executa chamada multimodal no OpenRouter usando modelo de mídia.

    Com `pool` + `empresa_id`, registra a execução na governança
    (`ia_execucao` + `ia_budget`) — sem eles a chamada funciona igual, só não
    registra (caminho da aba Testar e das tools do agente, que não carregam
    pool). Ver `registrar_custo_midia`.
    """
    api_key = settings.openrouter_api_key
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada")
    modelo_alvo = model or settings.openrouter_midia_model
    payload: dict = {
        "model": modelo_alvo,
        "messages": messages,
        # Pede o custo REAL cobrado dentro do `usage` da resposta
        # (mig 139: usage.cost é a verdade — a tabela local chegou a
        # superestimar 91%). Sem isto o gasto de mídia seguia
        # invisível ao ia_budget.
        "usage": {"include": True},
    }
    # ADR-001: modelo de peso aberto ganha piso de quantização; proprietário
    # segue sem bloco `provider` (o default do OpenRouter já é o ótimo).
    prefs = provider_preferences(modelo_alvo)
    if prefs is not None:
        payload["provider"] = prefs
    inicio = time.monotonic()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json=payload,
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
        # Variante do mesmo gotcha (API reference): o erro também pode vir
        # DENTRO de `choices[0].error` num HTTP 200 — sem esta checagem ele
        # viraria content vazio silencioso, o mesmo destino do atendimento 574.
        primeira = result["choices"][0]
        erro_choice = primeira.get("error")
        if erro_choice:
            detalhe = (
                erro_choice.get("message")
                if isinstance(erro_choice, dict)
                else str(erro_choice)
            ) or str(erro_choice)[:200]
            raise RuntimeError(f"OpenRouter recusou a chamada de mídia: {detalhe}")
        content = primeira["message"].get("content")
        if pool is not None and empresa_id is not None:
            await registrar_custo_midia(
                pool,
                empresa_id,
                # `result["model"]` é o modelo que atendeu de fato (roteamento);
                # cai pro solicitado se o campo não vier.
                modelo=result.get("model") or model or settings.openrouter_midia_model,
                usage=result.get("usage"),
                generation_id=result.get("id"),
                duracao_ms=int((time.monotonic() - inicio) * 1000),
                finalidade=finalidade,
            )
        return _extract_text(content).strip()


async def describe_image_bytes(
    media_bytes: bytes,
    media_type: str,
    model: str | None = None,
    focus: str | None = None,
    *,
    pool: AsyncConnectionPool | None = None,
    empresa_id: int | None = None,
) -> str:
    """Descreve imagem (ou responde pergunta direcionada via `focus`).

    Sem `focus`: descrição seca em 1-3 frases.
    Com `focus`: responde pergunta específica olhando a imagem.
    `pool` + `empresa_id` ligam o registro de custo na governança.
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
        pool=pool,
        empresa_id=empresa_id,
        finalidade="visao_imagem",
    )


async def transcribe_audio_bytes(
    media_bytes: bytes,
    media_type: str,
    model: str | None = None,
    *,
    pool: AsyncConnectionPool | None = None,
    empresa_id: int | None = None,
    finalidade: str = "transcricao_audio",
) -> str:
    """Transcreve áudio literalmente em pt-BR.

    `pool` + `empresa_id` ligam o registro de custo na governança. `finalidade`
    separa esse custo por caminho no `ia_execucao` — a verificação de fidelidade
    da voz (`shared/voz.py`) transcreve pra conferir e não é transcrição de
    mensagem de cliente.
    """
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
        pool=pool,
        empresa_id=empresa_id,
        finalidade=finalidade,
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
