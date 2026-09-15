"""Tests pra agents/tools/midia.py — 4 tools multimodais.

Mocks: download_media + chat_completion_media + extract_text + create_chat_model.
Não chama OpenRouter real (usaria créditos + flaky).

Contrato das tools (fix dd26aff — "agente alucinava URL"): a `media_url` do
turno NÃO é parâmetro da tool; é injetada via RunnableConfig em
`config={"configurable": {"media_url": ...}}`. Os testes invocam as tools com
esse config; sem ele a tool retorna "[ERRO: Nenhuma mídia anexada]".
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.agents.tools.midia import (
    _get_media_url,
    analyze_image,
    extract_document,
    summarize_document,
    transcribe_audio,
)


def _cfg(media_url: str) -> dict:
    """RunnableConfig que injeta a media_url do turno (igual ao worker)."""
    return {"configurable": {"media_url": media_url}}


class TestAnalyzeImage:
    async def test_chama_describe_image_url_sem_focus(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(return_value="Descrição da imagem"),
        ) as m:
            r = await analyze_image.ainvoke({}, config=_cfg("https://x/img.png"))
            assert r == "Descrição da imagem"
            m.assert_awaited_once_with("https://x/img.png", focus=None)

    async def test_propaga_focus(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(return_value="42"),
        ) as m:
            r = await analyze_image.ainvoke(
                {"focus": "qual o número?"}, config=_cfg("https://x/i.png")
            )
            assert r == "42"
            m.assert_awaited_once_with("https://x/i.png", focus="qual o número?")

    async def test_falha_retorna_msg_erro_sem_levantar(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            r = await analyze_image.ainvoke({}, config=_cfg("https://x/i.png"))
            assert r.startswith("[ERRO")
            assert "boom" in r


class TestTranscribeAudio:
    async def test_chama_transcribe_audio_url(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.transcribe_audio_url",
            new=AsyncMock(return_value="texto cru"),
        ) as m:
            r = await transcribe_audio.ainvoke({}, config=_cfg("https://x/a.ogg"))
            assert r == "texto cru"
            m.assert_awaited_once_with("https://x/a.ogg")

    async def test_falha_retorna_msg_erro(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.transcribe_audio_url",
            new=AsyncMock(side_effect=ValueError("audio inválido")),
        ):
            r = await transcribe_audio.ainvoke({}, config=_cfg("https://x/a.ogg"))
            assert r.startswith("[ERRO")


class TestExtractDocument:
    async def test_pdf_extract_text(self):
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"%PDF-1.4...", "application/pdf")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value="Texto do PDF"),
            ) as m_ext,
        ):
            r = await extract_document.ainvoke({}, config=_cfg("https://x/d.pdf"))
            assert r == "Texto do PDF"
            # Confere que filename foi inferido como doc.pdf
            args, kwargs = m_ext.call_args
            assert args[0] == "doc.pdf"

    async def test_docx_filename(self):
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(
                    return_value=(
                        b"PK\x03\x04...",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                ),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value="Texto do DOCX"),
            ) as m_ext,
        ):
            await extract_document.ainvoke({}, config=_cfg("https://x/c.docx"))
            args, _ = m_ext.call_args
            assert args[0] == "doc.docx"

    async def test_truncamento(self):
        big = "A" * 100_000
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"x", "application/pdf")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value=big),
            ),
        ):
            r = await extract_document.ainvoke({}, config=_cfg("https://x/d.pdf"))
            assert "[...truncado em" in r
            # Truncado em 30k chars + msg
            assert len(r) < 31_000

    async def test_documento_vazio(self):
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"x", "application/pdf")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value=""),
            ),
        ):
            r = await extract_document.ainvoke({}, config=_cfg("https://x/d.pdf"))
            assert "sem texto" in r


class TestSummarizeDocument:
    # `extract_document` é uma StructuredTool (pydantic frozen) — não dá pra
    # `patch.object(extract_document, "ainvoke", ...)`. Em vez disso mockamos os
    # deps reais (download_media + extract_text) e deixamos a tool interna rodar.
    async def test_chama_extract_e_resume(self):
        class FakeResp:
            content = "• Bullet 1\n• Bullet 2"

        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"%PDF...", "application/pdf")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value="Texto longo do documento"),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.create_chat_model",
            ) as m_llm,
        ):
            m_llm.return_value.ainvoke = AsyncMock(return_value=FakeResp())
            r = await summarize_document.ainvoke({}, config=_cfg("https://x/d.pdf"))
            assert "Bullet 1" in r

    async def test_focus_propagado_no_prompt(self):
        class FakeResp:
            content = "resumo focado"

        captured_prompt = []

        async def captura(prompt):
            captured_prompt.append(prompt)
            return FakeResp()

        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"%PDF...", "application/pdf")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value="Conteúdo X"),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.create_chat_model",
            ) as m_llm,
        ):
            m_llm.return_value.ainvoke = AsyncMock(side_effect=captura)
            await summarize_document.ainvoke(
                {"focus": "valor total"}, config=_cfg("https://x/d.pdf")
            )
            assert any("valor total" in p for p in captured_prompt)

    async def test_propaga_erro_da_extract(self):
        # download_media falha → extract_document retorna "[ERRO: ...]" →
        # summarize_document propaga sem chamar o LLM.
        with patch(
            "whatsapp_langchain.agents.tools.midia.download_media",
            new=AsyncMock(side_effect=RuntimeError("download falhou")),
        ):
            r = await summarize_document.ainvoke({}, config=_cfg("https://x/d.pdf"))
            assert r.startswith("[ERRO")


def _pool_fake(row):
    """Pool cujo `connection()` entrega uma conn que responde `row` ao SELECT."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=row)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()

    @asynccontextmanager
    async def _connection():
        yield conn

    pool.connection = _connection
    return pool, conn


def _runtime(**configurable) -> SimpleNamespace:
    return SimpleNamespace(config={"configurable": configurable})


class TestGetMediaUrl:
    """Fase 1 dos checkpoints: a mídia inline vem pela referência, não pelo config.

    O worker só põe `media_url` no configurable quando é http(s); `data:...`
    fica na fila e a tool lê por `message_queue_id`. Sem isso o base64 ia
    parar em `checkpoints.metadata` a cada passo do agente.
    """

    async def test_url_no_config_nao_consulta_a_fila(self):
        with patch("whatsapp_langchain.agents.tools.midia.get_pool") as gp:
            r = await _get_media_url(
                _runtime(media_url="https://x/a.ogg", message_queue_id=42)
            )
            assert r == "https://x/a.ogg"
            gp.assert_not_called()

    async def test_sem_url_resolve_pela_referencia_na_fila(self):
        pool, conn = _pool_fake(("data:audio/ogg;base64,AAAA", None, "audio/ogg"))
        with patch(
            "whatsapp_langchain.agents.tools.midia.get_pool",
            new=AsyncMock(return_value=pool),
        ):
            r = await _get_media_url(
                _runtime(media_url=None, message_queue_id=42, empresa_id=1018)
            )
        assert r == "data:audio/ogg;base64,AAAA"
        sql, params = conn.execute.await_args.args
        assert "message_queue" in sql and "empresa_id" in sql
        assert params == (42, 1018)

    async def test_sem_url_nem_referencia_e_none(self):
        with patch("whatsapp_langchain.agents.tools.midia.get_pool") as gp:
            assert await _get_media_url(_runtime(media_url=None)) is None
            gp.assert_not_called()

    async def test_row_sem_midia_e_none(self):
        pool, _ = _pool_fake((None, None, None))
        with patch(
            "whatsapp_langchain.agents.tools.midia.get_pool",
            new=AsyncMock(return_value=pool),
        ):
            assert await _get_media_url(_runtime(message_queue_id=42)) is None

    async def test_falha_no_banco_vira_none_sem_levantar(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.get_pool",
            new=AsyncMock(side_effect=RuntimeError("pool fechado")),
        ):
            assert await _get_media_url(_runtime(message_queue_id=42)) is None

    async def test_tool_transcreve_a_midia_lida_da_fila(self):
        """Fim a fim: config só com a referência → a tool chega no base64."""
        pool, _ = _pool_fake(("data:audio/ogg;base64,QUJD", None, "audio/ogg"))
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.get_pool",
                new=AsyncMock(return_value=pool),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.transcribe_audio_url",
                new=AsyncMock(return_value="texto do áudio"),
            ) as m,
        ):
            r = await transcribe_audio.ainvoke(
                {},
                config={"configurable": {"message_queue_id": 42, "empresa_id": 1}},
            )
        assert r == "texto do áudio"
        m.assert_awaited_once_with("data:audio/ogg;base64,QUJD")

    async def test_referencia_de_storage_vira_data_url(self):
        """mig 184: media_url NULL + media_arquivo_uuid → resolve pelo storage,
        materializando os bytes num data: URL (o modelo precisa inline)."""
        from whatsapp_langchain.shared.models import Arquivo

        pool, _ = _pool_fake((None, "uuid-1", "image/png"))
        arq = Arquivo(uuid="uuid-1", empresa_id=1, bucket="b", object_key="k.png")
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.get_pool",
                new=AsyncMock(return_value=pool),
            ),
            patch(
                "whatsapp_langchain.shared.arquivo.get_arquivo",
                new=AsyncMock(return_value=arq),
            ),
            patch(
                "whatsapp_langchain.shared.storage.ler_bytes",
                new=AsyncMock(return_value=b"PNGBYTES"),
            ),
        ):
            r = await _get_media_url(
                _runtime(media_url=None, message_queue_id=42, empresa_id=1)
            )
        import base64 as _b64

        assert r == "data:image/png;base64," + _b64.b64encode(b"PNGBYTES").decode()


# Marca todos como asyncio (conftest já configura asyncio_mode=auto)
pytestmark = pytest.mark.asyncio
