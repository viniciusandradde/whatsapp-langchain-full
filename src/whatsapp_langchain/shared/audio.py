"""Nota de voz em qualquer formato → OGG/Opus (o que o WhatsApp aceita como PTT).

O WhatsApp só reconhece nota de voz (bolha com player e forma de onda) em
**OGG/Opus**. O app Android grava direto nesse formato, mas o navegador não
tem essa opção: o `MediaRecorder` do Chrome/Android grava WebM/Opus, o do
Firefox OGG/Opus e o do Safari/iPhone MP4/AAC. Mandar WebM ou AAC por
`sendWhatsAppAudio` chega como arquivo — ou nem chega.

Por isso a conversão mora AQUI, no servidor, antes do `send_audio`: o painel
manda o que gravou e o cliente recebe a nota de voz certa, seja qual for o
navegador. É o mesmo PyAV (`libopus`) da voz do agente (`shared/voz.py`),
generalizado para decodificar qualquer contêiner que ele abra.

Três regras:
- **OGG/Opus entra e sai igual** (Firefox, app): reconhecido pelo próprio
  demuxer, não pelo MIME que o navegador declarou — `audio/ogg` pode ser
  Vorbis, e `audio/webm` pode vir rotulado de `video/webm`. Exceto quando a
  faixa não começa no zero (regra abaixo): aí recodifica.
- **A saída sempre começa em t=0.** O `MediaRecorder` do Chrome/Android
  carimba o WebM com o relógio do microfone (desde que a página abriu o
  stream), não com zero: uma nota de 5 s gravada 20 min depois de abrir a
  conversa chegava com pts de 1238 s a 1243 s, e o player mostrava "20:43"
  (medido no dev em 2026-09-19, mensagem 5893). Os pts são reatribuídos do
  zero, contando amostras, antes de codificar — o granule do OGG passa a
  dizer a duração da fala, que é o que o WhatsApp e o painel exibem.
- **Síncrono e CPU-bound**: quem chama roda via `asyncio.to_thread`. WebM/Opus
  recodifica em fração do tempo real; MP4/AAC de 5 min leva segundos.
"""

from __future__ import annotations

import io
from fractions import Fraction

import structlog

logger = structlog.get_logger()

MIME_NOTA_DE_VOZ = "audio/ogg"

_OPUS_RATE = 48000
_OPUS_BIT_RATE = 32000
# Faixa que começa depois disto (em segundos) não passa intacta: é o caso do
# relógio do microfone acima. Abaixo disso é o pre-skip do Opus e ruído de
# arredondamento, e o player já trata.
_TOLERANCIA_INICIO_S = 0.5


class AudioInvalidoError(Exception):
    """O arquivo não é um áudio que o decodificador consiga abrir."""


def _e_ogg_opus(container) -> bool:
    fmt = (container.format.name or "").lower()
    if "ogg" not in fmt:
        return False
    try:
        stream = container.streams.audio[0]
    except IndexError:
        return False
    return (stream.codec_context.name or "").lower() == "opus"


def _comeca_no_zero(container) -> bool:
    """A faixa de áudio começa (perto de) t=0? `start_time` vem em `time_base`."""
    stream = container.streams.audio[0]
    inicio = stream.start_time
    if inicio is None:
        return True
    return abs(float(inicio * stream.time_base)) <= _TOLERANCIA_INICIO_S


def converter_para_nota_de_voz(dados: bytes) -> tuple[bytes, str]:
    """Decodifica `dados` (WebM/MP4/OGG/MP3/WAV…) e devolve `(ogg_opus, "audio/ogg")`.

    Já é OGG/Opus e começa no zero → devolve os bytes originais sem tocar
    (remux à toa perderia o cabeçalho que o app grava certo). Áudio que o
    PyAV não abre, ou sem faixa de áudio, levanta `AudioInvalidoError` — o
    chamador transforma em 400 legível em vez de mandar lixo pro WhatsApp.
    """
    import av
    from av.error import FFmpegError  # type: ignore[attr-defined]

    if not dados:
        raise AudioInvalidoError("Áudio vazio.")

    try:
        entrada = av.open(io.BytesIO(dados), "r")
    except (FFmpegError, ValueError, OSError) as exc:
        raise AudioInvalidoError("Não foi possível ler o áudio.") from exc

    try:
        if not entrada.streams.audio:
            raise AudioInvalidoError("O arquivo não tem faixa de áudio.")
        if _e_ogg_opus(entrada) and _comeca_no_zero(entrada):
            return dados, MIME_NOTA_DE_VOZ

        origem = f"{entrada.format.name}/{entrada.streams.audio[0].codec_context.name}"
        buf = io.BytesIO()
        saida = av.open(buf, "w", format="ogg")
        stream = saida.add_stream("libopus", rate=_OPUS_RATE, layout="mono")
        stream.bit_rate = _OPUS_BIT_RATE  # type: ignore[attr-defined]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=_OPUS_RATE)
        base = Fraction(1, _OPUS_RATE)
        quadros = 0
        amostras = 0

        def codificar(f) -> None:
            # Reatribui o pts contando amostras: o relógio de origem (o do
            # microfone do navegador) não interessa — só a duração da fala.
            nonlocal quadros, amostras
            f.pts = amostras
            f.time_base = base
            amostras += f.samples
            saida.mux(stream.encode(f))  # type: ignore[arg-type]
            quadros += 1

        try:
            for frame in entrada.decode(audio=0):
                for f in resampler.resample(frame):
                    codificar(f)
            for f in resampler.resample(None):
                codificar(f)
            saida.mux(stream.encode(None))  # type: ignore[arg-type]
        except (FFmpegError, ValueError) as exc:
            raise AudioInvalidoError(
                "O áudio está corrompido ou num codec sem suporte."
            ) from exc
        finally:
            saida.close()
        if quadros == 0:
            raise AudioInvalidoError("O áudio não tem conteúdo.")
        convertido = buf.getvalue()
        logger.info(
            "nota_de_voz_convertida",
            origem=origem,
            bytes_entrada=len(dados),
            bytes_saida=len(convertido),
        )
        return convertido, MIME_NOTA_DE_VOZ
    finally:
        entrada.close()
