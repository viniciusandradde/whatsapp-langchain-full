"""`transcrever_mensagem` (mig 169) — de onde vem o áudio.

Cobre o buraco aberto pelas migs 183/184: com object storage ligado,
`media_url` fica NULL de propósito e a mensagem guarda só
`media_arquivo_uuid`. O botão "Transcrever" recusava TODO áudio novo com
"Esta mensagem não tem áudio para transcrever" (produção, atendimento
1-000796, 2026-09-17). Nada aqui chama OpenRouter nem MinIO.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared.models import Arquivo
from whatsapp_langchain.shared.transcricao import (
    MensagemSemAudioError,
    transcrever_mensagem,
)

# Linha lida da message_queue:
# (media_url, media_arquivo_uuid, media_type, transcricao, empresa_id)


def _pool_fake(*rows):
    """`fetchone` devolve `rows` em sequência: o SELECT da mensagem e, quando
    a transcrição acontece, a releitura depois do UPDATE."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=list(rows))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()

    @asynccontextmanager
    async def _connection():
        yield conn

    pool.connection = _connection
    return pool, conn


def _patch_provedor(texto: str = "texto do áudio"):
    return patch(
        "whatsapp_langchain.shared.transcricao.transcribe_audio_bytes",
        new=AsyncMock(return_value=texto),
    )


async def test_audio_no_bucket_resolve_pela_referencia():
    """media_url NULL + media_arquivo_uuid → lê do storage e transcreve."""
    pool, _ = _pool_fake(
        (None, "uuid-1", "audio/ogg; codecs=opus", None, 1),
        ("texto do áudio",),
    )
    arq = Arquivo(
        uuid="uuid-1",
        empresa_id=1,
        bucket="b",
        object_key="k.ogg",
        mime_type="audio/ogg",
    )
    with (
        patch(
            "whatsapp_langchain.shared.arquivo.get_arquivo",
            new=AsyncMock(return_value=arq),
        ) as get_arquivo,
        patch(
            "whatsapp_langchain.shared.storage.ler_bytes",
            new=AsyncMock(return_value=b"OGGBYTES"),
        ),
        _patch_provedor() as provedor,
    ):
        r = await transcrever_mensagem(pool, 7195, empresa_id=1, atendimento_id=796)

    assert r == "texto do áudio"
    get_arquivo.assert_awaited_once_with(pool, "uuid-1")
    # Os bytes do bucket chegam intactos ao provedor, com o mime do arquivo.
    assert provedor.await_args.args[0] == b"OGGBYTES"
    assert provedor.await_args.args[1] == "audio/ogg"


async def test_audio_inline_continua_funcionando():
    """Caminho antigo (storage desligado / fallback base64) não muda."""
    pool, _ = _pool_fake(
        ("data:audio/ogg;base64,T2dnUw==", None, "audio/ogg", None, 1),
        ("texto do áudio",),
    )
    with (
        patch("whatsapp_langchain.shared.arquivo.get_arquivo") as get_arquivo,
        _patch_provedor() as provedor,
    ):
        r = await transcrever_mensagem(pool, 1, empresa_id=1)

    assert r == "texto do áudio"
    get_arquivo.assert_not_called()
    assert provedor.await_args.args[0] == b"OggS"


async def test_ja_transcrita_nao_toca_no_storage():
    """Idempotência vale antes de qualquer resolução de mídia."""
    pool, _ = _pool_fake((None, "uuid-1", "audio/ogg", "já transcrito", 1))
    with (
        patch("whatsapp_langchain.shared.arquivo.get_arquivo") as get_arquivo,
        _patch_provedor() as provedor,
    ):
        assert await transcrever_mensagem(pool, 1) == "já transcrito"
    get_arquivo.assert_not_called()
    provedor.assert_not_called()


@pytest.mark.parametrize(
    "row",
    [
        (None, None, "audio/ogg", None, 1),  # sem URL e sem referência
        (None, "uuid-1", "image/png", None, 1),  # referência, mas não é áudio
        ("data:image/png;base64,AA==", None, "image/png", None, 1),
    ],
)
async def test_sem_audio_recusa(row):
    pool, _ = _pool_fake(row)
    with (
        patch("whatsapp_langchain.shared.arquivo.get_arquivo") as get_arquivo,
        _patch_provedor() as provedor,
        pytest.raises(MensagemSemAudioError, match="não tem áudio"),
    ):
        await transcrever_mensagem(pool, 1)
    get_arquivo.assert_not_called()
    provedor.assert_not_called()


async def test_referencia_orfa_recusa_sem_chamar_provedor():
    """`media_arquivo_uuid` apontando pra linha que já não existe em `arquivo`
    (retenção apagou) — recusa legível, não 500."""
    pool, _ = _pool_fake((None, "uuid-sumido", "audio/ogg", None, 1))
    with (
        patch(
            "whatsapp_langchain.shared.arquivo.get_arquivo",
            new=AsyncMock(return_value=None),
        ),
        patch("whatsapp_langchain.shared.storage.ler_bytes") as ler_bytes,
        _patch_provedor() as provedor,
        pytest.raises(MensagemSemAudioError, match="não tem áudio"),
    ):
        await transcrever_mensagem(pool, 1)
    ler_bytes.assert_not_called()
    provedor.assert_not_called()
