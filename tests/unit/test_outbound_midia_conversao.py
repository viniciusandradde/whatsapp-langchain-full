"""`send_outbound_manual_midia` converte a nota de voz antes de mandar.

O que está em jogo: o painel web grava WebM (Chrome) ou MP4 (Safari), e o
cliente tem que receber OGG/Opus — pelo `send_audio`, com o banco guardando o
MESMO áudio convertido (a bolha do painel toca o que o cliente ouviu). Anexo
que não é áudio não passa pela conversão.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.shared.audio import AudioInvalidoError
from whatsapp_langchain.shared.outbound import (
    OutboundError,
    send_outbound_manual_midia,
)

_MOD = "whatsapp_langchain.shared.outbound"


def _destino():
    atendimento = SimpleNamespace(
        id=1, conexao_id=5, agente_atual="agente", status="em_andamento"
    )
    cliente = SimpleNamespace(telefone="+5567999990000")
    conexao = SimpleNamespace(id=5, provider="evolution")
    return atendimento, cliente, conexao


class _ClienteFalso:
    def __init__(self) -> None:
        self.audio: list[str] = []
        self.media: list[dict] = []

    async def send_audio(self, to: str, audio: str) -> str:
        self.audio.append(audio)
        return "mid-audio"

    async def send_media(self, to: str, media: str, **kw) -> str:
        self.media.append({"media": media, **kw})
        return "mid-media"


async def _enviar(arquivo: bytes, mime: str, *, conversor):
    cliente = _ClienteFalso()
    persist = AsyncMock(return_value={"id": 99})
    with (
        patch(f"{_MOD}._resolver_destino", new=AsyncMock(return_value=_destino())),
        patch(f"{_MOD}._build_client", new=AsyncMock(return_value=(cliente, "mock"))),
        patch(f"{_MOD}._persist_outbound_row", new=persist),
        patch(f"{_MOD}.converter_para_nota_de_voz", new=conversor),
    ):
        row = await send_outbound_manual_midia(
            AsyncMock(),
            atendimento_id=1,
            empresa_id=1,
            user_id="u1",
            arquivo=arquivo,
            mime=mime,
            filename="x",
            legenda="",
        )
    return row, cliente, persist


async def test_audio_webm_vira_ogg_no_envio_e_no_banco() -> None:
    webm = b"\x1aE\xdf\xa3webm-falso"
    ogg = b"OggS-opus-convertido"
    conversor = lambda dados: (ogg, "audio/ogg")  # noqa: E731

    row, cliente, persist = await _enviar(webm, "audio/webm", conversor=conversor)

    assert row == {"id": 99}
    # O que foi pro WhatsApp é o OGG convertido, em base64 puro.
    assert cliente.audio == [base64.b64encode(ogg).decode("ascii")]
    assert cliente.media == []
    # E o banco guarda o mesmo áudio, com o MIME certo — não o WebM original.
    kw = persist.await_args.kwargs
    assert kw["media_type"] == "audio/ogg"
    assert (
        kw["media_url"]
        == f"data:audio/ogg;base64,{base64.b64encode(ogg).decode('ascii')}"
    )


async def test_imagem_nao_passa_pela_conversao() -> None:
    chamado = []

    def conversor(dados):
        chamado.append(dados)
        raise AssertionError("imagem não converte")

    row, cliente, persist = await _enviar(b"\x89PNG", "image/png", conversor=conversor)

    assert chamado == []
    assert cliente.audio == []
    assert cliente.media and cliente.media[0]["mediatype"] == "image"
    assert persist.await_args.kwargs["media_type"] == "image/png"
    # O nome real do arquivo vai pro banco (mig 186) — é o que a timeline mostra.
    assert persist.await_args.kwargs["media_filename"] == "x"


async def test_nota_de_voz_nao_guarda_nome() -> None:
    """ "nota-de-voz.webm" não interessa a ninguém e o formato mudou pra OGG."""
    conversor = lambda dados: (b"OggS", "audio/ogg")  # noqa: E731
    _, _, persist = await _enviar(b"\x1aE", "audio/webm", conversor=conversor)
    assert persist.await_args.kwargs["media_filename"] is None


def test_nome_de_arquivo_seguro() -> None:
    from whatsapp_langchain.shared.outbound import nome_de_arquivo_seguro

    assert nome_de_arquivo_seguro("orçamento final.pdf") == "orçamento final.pdf"
    # Caminho inteiro (Windows antigo / navegador esquisito) → só o nome.
    assert nome_de_arquivo_seguro("C:\\Users\\x\\rel.xlsx") == "rel.xlsx"
    assert nome_de_arquivo_seguro("/tmp/a/b.png") == "b.png"
    assert nome_de_arquivo_seguro('a"b\nc.pdf') == "abc.pdf"
    assert nome_de_arquivo_seguro("") is None
    assert nome_de_arquivo_seguro(None) is None
    assert len(nome_de_arquivo_seguro("x" * 300) or "") == 255


async def test_audio_invalido_vira_outbound_error_antes_de_enviar() -> None:
    def conversor(dados):
        raise AudioInvalidoError("Não foi possível ler o áudio.")

    with pytest.raises(OutboundError, match="Não foi possível ler o áudio"):
        await _enviar(b"lixo", "audio/webm", conversor=conversor)
