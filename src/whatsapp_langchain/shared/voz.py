"""Voz do agente — síntese de fala (TTS) pra nota de voz do WhatsApp (mig 176).

Caminho inverso de `shared/transcricao.py`: aqui o texto do agente vira áudio.
O provedor é o OpenRouter (`settings.tts_model`, default openai/gpt-audio-mini),
que **exige stream=true e só entrega pcm16** — a conversão pra OGG/Opus 48kHz
mono (o único formato que o WhatsApp aceita como nota de voz, ver
`worker/evolution_client.py::send_audio`) é feita aqui com PyAV, cuja wheel
traz FFmpeg embutido e roda sem apt.

Custo visível desde o primeiro dia: quando `pool`+`empresa_id` são passados,
o `usage.cost` do último evento SSE entra em `ia_execucao` + `ia_budget`
(`shared/governanca_ia.py`) — a transcrição nasceu como gasto invisível e é o
erro que não queremos repetir. Best-effort: falha no registro só loga, nunca
propaga (contrato mig 164).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time

import httpx
import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.governanca_ia import (
    CUSTO_FONTE_OPENROUTER,
    acrescentar_consumo,
    registrar_execucao,
)
from whatsapp_langchain.shared.outbound import MIDIA_MAX_BYTES

logger = structlog.get_logger()

# Catálogo das 8 vozes do gpt-audio-mini com rótulo pt-BR pro select da UI.
# Fonte única — a rota de preview e o PATCH da empresa validam contra isto.
VOZES: dict[str, str] = {
    "alloy": "Alloy (neutra)",
    "ash": "Ash (masculina firme)",
    "ballad": "Ballad (suave)",
    "coral": "Coral (feminina calorosa)",
    "echo": "Echo (masculina)",
    "sage": "Sage (feminina serena)",
    "shimmer": "Shimmer (feminina energética)",
    "verse": "Verse (expressiva)",
}

VOZ_DEFAULT = "alloy"

# Acima disto não sintetiza: áudio longo é ruim de ouvir e caro.
VOZ_TEXTO_MAX_CHARS = 1500

# Anti-comentário: no teste real o modelo disse "Claro! Vou ler o texto
# agora:" antes de ler. A instrução é imperativa de propósito.
SYSTEM_PROMPT_VOZ = (
    "Você é um sintetizador de voz. Fale EXATAMENTE o texto enviado pelo "
    "usuário, em português do Brasil, sem adicionar, comentar ou responder nada."
)

# O gpt-audio-mini entrega PCM16 a 24kHz mono; o WhatsApp quer Opus 48kHz.
_PCM_RATE = 24000
_OPUS_RATE = 48000
_OPUS_BIT_RATE = 32000


class VozError(Exception):
    """Falha na síntese de voz (provedor, formato ou tamanho)."""


class VozTextoLongoError(VozError):
    """Texto acima de VOZ_TEXTO_MAX_CHARS — não sintetiza."""


def _pcm16_para_ogg_opus(pcm: bytes) -> bytes:
    """PCM16 24kHz mono → OGG/Opus 48kHz mono (nota de voz do WhatsApp).

    Síncrono e CPU-bound — o chamador roda via `asyncio.to_thread`.
    """
    import av

    buf = io.BytesIO()
    saida = av.open(buf, "w", format="ogg")
    stream = saida.add_stream("libopus", rate=_OPUS_RATE, layout="mono")
    stream.bit_rate = _OPUS_BIT_RATE  # type: ignore[attr-defined]
    entrada = av.open(
        io.BytesIO(pcm),
        "r",
        format="s16le",
        options={"ar": str(_PCM_RATE), "ac": "1"},
    )
    resampler = av.AudioResampler(format="s16", layout="mono", rate=_OPUS_RATE)
    for frame in entrada.decode(audio=0):
        for f in resampler.resample(frame):
            saida.mux(stream.encode(f))  # type: ignore[arg-type]
    saida.mux(stream.encode(None))  # type: ignore[arg-type]
    saida.close()
    entrada.close()
    return buf.getvalue()


async def _registrar_custo(
    pool: AsyncConnectionPool,
    empresa_id: int,
    usage: dict,
    duracao_ms: int,
) -> None:
    """Grava a execução TTS em ia_execucao + soma no ia_budget do mês.

    Best-effort por contrato: registro de custo NUNCA derruba a resposta
    falada (nem o fallback pra texto) — falha só loga.
    """
    try:
        custo_raw = usage.get("cost")
        custo = float(custo_raw) if custo_raw is not None else None
        provedor, _, nome = settings.tts_model.partition("/")
        await registrar_execucao(
            pool,
            empresa_id=empresa_id,
            modelo_provedor=provedor or "openrouter",
            modelo_nome=nome or settings.tts_model,
            tokens_input=int(usage.get("prompt_tokens") or 0),
            tokens_output=int(usage.get("completion_tokens") or 0),
            custo_total=custo,
            duracao_ms=duracao_ms,
            status="success",
            metadata={"origem": "voz"},
            custo_fonte=CUSTO_FONTE_OPENROUTER if custo is not None else None,
        )
        if custo is not None and custo > 0:
            await acrescentar_consumo(pool, empresa_id, custo)
    except Exception as exc:
        logger.warning(
            "voz_registro_custo_falhou", empresa_id=empresa_id, error=str(exc)
        )


async def sintetizar(
    texto: str,
    *,
    voz: str = VOZ_DEFAULT,
    estilo: str = "",
    pool: AsyncConnectionPool | None = None,
    empresa_id: int | None = None,
) -> bytes:
    """Sintetiza `texto` e devolve OGG/Opus pronto pra `send_audio`.

    - Texto acima de VOZ_TEXTO_MAX_CHARS → VozTextoLongoError (quem chama
      decide o fallback — no worker, a resposta segue em texto).
    - Voz fora de VOZES cai em `alloy` com warning (não falha: voz errada
      gravada no banco não pode calar o recurso inteiro).
    - `estilo` (texto livre, ex. "fale com calma, tom acolhedor") entra no
      system prompt do sintetizador.
    - Com `pool`+`empresa_id`, o custo medido (`usage.cost` do SSE) entra em
      ia_execucao/ia_budget — best-effort, nunca propaga.

    Raises:
        VozTextoLongoError: texto longo demais.
        VozError: falha de provedor, resposta sem áudio, formato inesperado
            ou áudio acima de MIDIA_MAX_BYTES.
    """
    if len(texto) > VOZ_TEXTO_MAX_CHARS:
        raise VozTextoLongoError(
            f"Texto com {len(texto)} chars excede o teto de "
            f"{VOZ_TEXTO_MAX_CHARS} pra síntese de voz."
        )
    if voz not in VOZES:
        logger.warning("voz_desconhecida_usando_default", voz=voz)
        voz = VOZ_DEFAULT

    api_key = settings.resolved_tts_api_key
    if api_key is None:
        raise VozError("OPENROUTER_API_KEY/OPENROUTER_TTS_API_KEY não configurada.")

    system = SYSTEM_PROMPT_VOZ
    estilo = (estilo or "").strip()
    if estilo:
        system = f"{system} Estilo de fala: {estilo}"

    payload = {
        "model": settings.tts_model,
        "modalities": ["text", "audio"],
        "audio": {"voice": voz, "format": "pcm16"},
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": texto},
        ],
    }
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }

    inicio = time.monotonic()
    audio_b64: list[str] = []
    usage: dict = {}
    try:
        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream("POST", url, headers=headers, json=payload) as resp,
        ):
            if resp.status_code != 200:
                corpo = (await resp.aread()).decode("utf-8", errors="replace")
                raise VozError(f"TTS HTTP {resp.status_code}: {corpo[:300]}")
            async for linha in resp.aiter_lines():
                linha = linha.strip()
                if not linha.startswith("data: ") or linha == "data: [DONE]":
                    continue
                try:
                    evt = json.loads(linha[6:])
                except json.JSONDecodeError:
                    continue
                # OpenRouter devolve 200 com envelope de erro — gotcha
                # conhecido do repo (falha transitória de provedor).
                if evt.get("error"):
                    raise VozError(f"TTS erro do provedor: {evt['error']}")
                if evt.get("usage"):
                    usage = evt["usage"]
                for ch in evt.get("choices", []):
                    au = (ch.get("delta") or {}).get("audio") or {}
                    if au.get("data"):
                        audio_b64.append(au["data"])
    except VozError:
        raise
    except httpx.HTTPError as exc:
        raise VozError(f"TTS falha de rede: {exc}") from exc

    if not audio_b64:
        raise VozError("TTS não devolveu áudio (sem deltas audio.data no SSE).")

    try:
        pcm = base64.b64decode("".join(audio_b64))
        ogg = await asyncio.to_thread(_pcm16_para_ogg_opus, pcm)
    except VozError:
        raise
    except Exception as exc:
        raise VozError(f"Conversão PCM16→OGG/Opus falhou: {exc}") from exc

    if not ogg.startswith(b"OggS"):
        raise VozError("Áudio convertido não é OGG (magic OggS ausente).")
    if len(ogg) > MIDIA_MAX_BYTES:
        raise VozError(f"Áudio sintetizado ({len(ogg)} bytes) excede MIDIA_MAX_BYTES.")

    duracao_ms = int((time.monotonic() - inicio) * 1000)
    logger.info(
        "voz_sintetizada",
        voz=voz,
        chars=len(texto),
        pcm_bytes=len(pcm),
        ogg_bytes=len(ogg),
        duracao_ms=duracao_ms,
        custo=usage.get("cost"),
    )

    if pool is not None and empresa_id is not None:
        await _registrar_custo(pool, empresa_id, usage, duracao_ms)

    return ogg
