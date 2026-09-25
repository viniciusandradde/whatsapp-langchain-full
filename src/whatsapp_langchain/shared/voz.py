"""Voz do agente — síntese de fala (TTS) pra nota de voz do WhatsApp (mig 176).

Caminho inverso de `shared/transcricao.py`: aqui o texto do agente vira áudio.
O provedor é o OpenRouter (`settings.tts_model`, default openai/gpt-audio-mini),
que **exige stream=true e só entrega pcm16** — a conversão pra OGG/Opus 48kHz
mono (o único formato que o WhatsApp aceita como nota de voz, ver
`worker/evolution_client.py::send_audio`) é feita aqui com PyAV, cuja wheel
traz FFmpeg embutido e roda sem apt.

**O gpt-audio-mini NÃO é um TTS — é um modelo de chat que fala**, e o catálogo
do OpenRouter não tem TTS de verdade (`/audio/speech` dá 400; só `gpt-audio*`
e o Lyria, de música, emitem áudio). Isso custou um incidente em produção: no
atendimento 63 o cliente perguntou "quem é você?" e recebeu uma nota de voz
que **não respondia a pergunta** — o modelo tratou o texto do agente como uma
mensagem dirigida a ele e RESPONDEU em vez de LER. O painel mostrava o texto
certo, então a falha era invisível de dentro. Em 8 reproduções com os textos
reais a fidelidade média foi 0,63, com 5 saídas erradas (pior caso: 0,04).

Daí as duas defesas deste módulo, nesta ordem:

1. **O texto a falar vai na mensagem `system`**, dentro de `<texto>`, e o
   `user` carrega só a ordem de ler. Texto solto no papel de `user` é lido
   como fala dirigida ao modelo — é o que disparava a paráfrase. Medido nos
   mesmos textos: fidelidade média sobe de 0,63 pra 0,972 (11 de 12 ≥ 0,90).
2. **`verificar_fidelidade=True` confere o áudio antes de ele sair**: a nota
   de voz é transcrita de volta e comparada com o texto original. Divergiu (ou
   ganhou preâmbulo de conversa), levanta `VozInfielError` e quem chama manda
   o texto. Como (1) é um modelo generativo e não dá garantia formal, é esta
   rede que sustenta a promessa de que o cliente nunca ouve outra coisa.

Custo visível desde o primeiro dia: quando `pool`+`empresa_id` são passados,
o `usage.cost` do último evento SSE entra em `ia_execucao` + `ia_budget`
(`shared/governanca_ia.py`) — a transcrição nasceu como gasto invisível e é o
erro que não queremos repetir. Best-effort: falha no registro só loga, nunca
propaga (contrato mig 164).
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import io
import json
import re
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
from whatsapp_langchain.shared.midia_processing import transcribe_audio_bytes
from whatsapp_langchain.shared.openrouter_chave import chave_openrouter_tts
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

# O texto a falar entra AQUI, no system, não na mensagem do usuário — ver a
# defesa (1) no topo do módulo. A instrução é imperativa de propósito: no teste
# real o modelo chegou a dizer "Claro! Vou ler o texto agora:" antes de ler.
SYSTEM_PROMPT_VOZ = (
    "Você é um leitor de texto em voz alta. O TEXTO A LER, delimitado por "
    "<texto>, deve ser vocalizado palavra por palavra, do início ao fim, em "
    "português do Brasil, sem responder, sem resumir, sem comentar e sem "
    "acrescentar nada."
)

# A mensagem do usuário carrega só a ordem — nunca o conteúdo a falar.
USER_PROMPT_VOZ = "Leia o texto acima em voz alta agora."

# Abaixo disto o áudio não sai: a nota de voz substitui o texto (o cliente não
# recebe os dois), então áudio divergente é resposta perdida, não enfeite.
# Calibrado nos textos reais do incidente: as reescritas mediram 0,04 / 0,47 /
# 0,68 e as leituras boas nunca caíram abaixo de 0,88.
VOZ_FIDELIDADE_MINIMA = 0.85

# Muleta de conversa que o modelo prega na frente quando escorrega de volta pro
# papel de assistente ("Claro, vou repetir o que você disse: …"). Só conta como
# defeito quando o próprio texto não começa assim.
_PREAMBULOS_DE_CONVERSA = (
    "claro",
    "ok",
    "certo",
    "entendi",
    "entendido",
    "perfeito",
    "beleza",
    "com certeza",
    "tudo bem",
    "sem problema",
    "vou repetir",
    "vou ler",
)

# O gpt-audio-mini entrega PCM16 a 24kHz mono; o WhatsApp quer Opus 48kHz.
_PCM_RATE = 24000
_OPUS_RATE = 48000
_OPUS_BIT_RATE = 32000


class VozError(Exception):
    """Falha na síntese de voz (provedor, formato ou tamanho)."""


class VozTextoLongoError(VozError):
    """Texto acima de VOZ_TEXTO_MAX_CHARS — não sintetiza."""


class VozInfielError(VozError):
    """O áudio não diz o que o texto manda — não pode ser enviado.

    Não é falha de provedor: a síntese funcionou, mas o modelo reescreveu,
    resumiu ou respondeu ao texto. Quem chama cai pro texto.
    """


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


def _montar_mensagens(texto: str, estilo: str) -> list[dict]:
    """Mensagens do TTS: o texto vai no system, a ordem de ler vai no user.

    Inverter isso é o bug do incidente — ver defesa (1) no topo do módulo.
    """
    system = SYSTEM_PROMPT_VOZ
    if estilo:
        system = f"{system} Estilo de fala: {estilo}"
    return [
        {"role": "system", "content": f"{system}\n<texto>\n{texto}\n</texto>"},
        {"role": "user", "content": USER_PROMPT_VOZ},
    ]


def _normalizar_para_comparar(texto: str) -> str:
    """Reduz texto e transcrição ao que dá pra comparar: as palavras faladas.

    Some com o que nunca vira som (markdown, numeração de lista, pontuação) e
    com o que varia entre grafia e fala (caixa, espaços), pra que a diferença
    que sobrar seja de conteúdo — não de formatação.
    """
    t = re.sub(r"[*_`#~]+", " ", texto.lower())
    t = re.sub(r"\d+\s*[.)]", " ", t)  # "1." de lista não é falado como texto
    t = re.sub(r"[^0-9a-zà-ÿ ]+", " ", t)
    return " ".join(t.split())


def _preambulo_inventado(alvo_norm: str, ouvido_norm: str) -> str | None:
    """Muleta de conversa no começo do áudio que não existe no texto."""
    primeira_do_alvo = alvo_norm.split(" ", 1)[0] if alvo_norm else ""
    for p in _PREAMBULOS_DE_CONVERSA:
        if ouvido_norm.startswith(f"{p} ") and not primeira_do_alvo.startswith(p):
            return p
    return None


async def _verificar_fidelidade(
    ogg: bytes,
    texto: str,
    pool: AsyncConnectionPool | None,
    empresa_id: int | None,
) -> None:
    """Ouve o áudio gerado e recusa se ele não disser o que o texto manda.

    Defesa (2) do módulo: transcreve a nota de voz de volta e compara com o
    original. É a única garantia possível com um modelo generativo no meio —
    e ela é barata perto do estrago (uma transcrição, ~US$0,0002).

    Raises:
        VozInfielError: divergência de conteúdo ou preâmbulo inventado.
    """
    ouvido = await transcribe_audio_bytes(
        ogg,
        "audio/ogg",
        pool=pool,
        empresa_id=empresa_id,
        finalidade="voz_verificacao",
    )
    alvo_norm = _normalizar_para_comparar(texto)
    ouvido_norm = _normalizar_para_comparar(ouvido)
    if not ouvido_norm:
        raise VozInfielError("Verificação não conseguiu ouvir o áudio gerado.")

    similaridade = difflib.SequenceMatcher(None, alvo_norm, ouvido_norm).ratio()
    preambulo = _preambulo_inventado(alvo_norm, ouvido_norm)
    if similaridade < VOZ_FIDELIDADE_MINIMA or preambulo:
        logger.warning(
            "voz_infiel_ao_texto",
            similaridade=round(similaridade, 3),
            preambulo=preambulo,
            chars_texto=len(texto),
            # O que o cliente OUVIRIA — é o que permite entender a falha
            # depois, já que o áudio recusado não fica em lugar nenhum.
            ouvido=ouvido[:300],
        )
        motivo = (
            f"preâmbulo inventado ({preambulo!r})"
            if preambulo
            else f"similaridade {similaridade:.2f} < {VOZ_FIDELIDADE_MINIMA}"
        )
        raise VozInfielError(f"Áudio não corresponde ao texto: {motivo}.")

    logger.info("voz_fidelidade_ok", similaridade=round(similaridade, 3))


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
    verificar_fidelidade: bool = False,
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
    - `verificar_fidelidade=True` ouve o áudio antes de devolvê-lo e recusa o
      que não corresponde ao texto (defesa (2) do módulo). Ligue sempre que o
      áudio for falar com um cliente; desligado, a amostra da UI economiza a
      transcrição e os ~2s dela.

    Raises:
        VozTextoLongoError: texto longo demais.
        VozInfielError: com `verificar_fidelidade`, o áudio saiu dizendo outra
            coisa — o custo da síntese já foi registrado quando isso acontece.
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

    api_key = chave_openrouter_tts()  # ADR-007: chave da empresa, se houver
    if api_key is None:
        raise VozError("OPENROUTER_API_KEY/OPENROUTER_TTS_API_KEY não configurada.")

    payload = {
        "model": settings.tts_model,
        "modalities": ["text", "audio"],
        "audio": {"voice": voz, "format": "pcm16"},
        "stream": True,
        "messages": _montar_mensagens(texto, (estilo or "").strip()),
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

    # Depois do custo de propósito: a síntese foi cobrada mesmo quando o áudio
    # é recusado logo abaixo, e esconder isso do ia_budget seria gasto invisível.
    if verificar_fidelidade:
        await _verificar_fidelidade(ogg, texto, pool, empresa_id)

    return ogg
