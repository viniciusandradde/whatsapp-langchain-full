"""Contrato de `shared/audio.py::converter_para_nota_de_voz`.

O WhatsApp só aceita nota de voz em OGG/Opus, e cada navegador grava num
formato: aqui os três (WebM/Opus do Chrome, MP4/AAC do Safari, OGG/Opus do
Firefox e do app) viram exatamente o que o `sendWhatsAppAudio` espera. Os
áudios de teste são gerados pelo próprio PyAV — sem fixture binária no repo.
"""

from __future__ import annotations

import io
import math
import struct

import pytest

from whatsapp_langchain.shared.audio import (
    MIME_NOTA_DE_VOZ,
    AudioInvalidoError,
    converter_para_nota_de_voz,
)


def _pcm(segundos: float, rate: int) -> bytes:
    """Tom de 440 Hz em PCM16 mono."""
    n = int(rate * segundos)
    return b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n)
    )


def _gerar(fmt: str, codec: str, rate: int, segundos: float = 0.5) -> bytes:
    import av

    buf = io.BytesIO()
    saida = av.open(buf, "w", format=fmt)
    stream = saida.add_stream(codec, rate=rate, layout="mono")
    entrada = av.open(
        io.BytesIO(_pcm(segundos, rate)),
        "r",
        format="s16le",
        options={"ar": str(rate), "ac": "1"},
    )
    resampler = av.AudioResampler(
        format="fltp" if codec == "aac" else "s16", layout="mono", rate=rate
    )
    for frame in entrada.decode(audio=0):
        for f in resampler.resample(frame):
            saida.mux(stream.encode(f))  # type: ignore[arg-type]
    saida.mux(stream.encode(None))  # type: ignore[arg-type]
    saida.close()
    entrada.close()
    return buf.getvalue()


def _inspecionar(dados: bytes) -> tuple[str, str, int, int]:
    import av

    c = av.open(io.BytesIO(dados))
    st = c.streams.audio[0]
    canais = st.codec_context.layout.nb_channels
    return c.format.name, st.codec_context.name, st.rate or 0, canais


@pytest.mark.parametrize(
    ("fmt", "codec", "rate"),
    [
        ("webm", "libopus", 48000),  # Chrome / Android
        ("mp4", "aac", 44100),  # Safari / iPhone
        ("wav", "pcm_s16le", 16000),  # arquivo qualquer
    ],
)
def test_converte_para_ogg_opus_mono_48k(fmt: str, codec: str, rate: int) -> None:
    saida, mime = converter_para_nota_de_voz(_gerar(fmt, codec, rate))
    assert mime == MIME_NOTA_DE_VOZ
    container, codec_saida, rate_saida, canais = _inspecionar(saida)
    assert container == "ogg"
    assert codec_saida == "opus"
    assert rate_saida == 48000
    assert canais == 1


def test_ogg_opus_passa_intacto() -> None:
    """Firefox e o app já mandam certo: os bytes não podem ser tocados."""
    original = _gerar("ogg", "libopus", 48000)
    saida, mime = converter_para_nota_de_voz(original)
    assert saida == original
    assert mime == MIME_NOTA_DE_VOZ


def test_lixo_nao_vira_nota_de_voz() -> None:
    with pytest.raises(AudioInvalidoError):
        converter_para_nota_de_voz(b"isto nao e audio" * 200)


def test_vazio_e_recusado() -> None:
    with pytest.raises(AudioInvalidoError):
        converter_para_nota_de_voz(b"")
