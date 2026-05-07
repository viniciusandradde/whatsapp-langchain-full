"""Tests pra agents/tools/midia.py — 4 tools multimodais.

Mocks: download_media + chat_completion_media + extract_text + create_chat_model.
Não chama OpenRouter real (usaria créditos + flaky).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.agents.tools.midia import (
    analyze_image,
    extract_document,
    summarize_document,
    transcribe_audio,
)


class TestAnalyzeImage:
    async def test_chama_describe_image_url_sem_focus(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(return_value="Descrição da imagem"),
        ) as m:
            r = await analyze_image.ainvoke({"image_url": "https://x/img.png"})
            assert r == "Descrição da imagem"
            m.assert_awaited_once_with("https://x/img.png", focus=None)

    async def test_propaga_focus(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(return_value="42"),
        ) as m:
            r = await analyze_image.ainvoke(
                {"image_url": "https://x/i.png", "focus": "qual o número?"}
            )
            assert r == "42"
            m.assert_awaited_once_with("https://x/i.png", focus="qual o número?")

    async def test_falha_retorna_msg_erro_sem_levantar(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.describe_image_url",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            r = await analyze_image.ainvoke({"image_url": "https://x/i.png"})
            assert r.startswith("[ERRO")
            assert "boom" in r


class TestTranscribeAudio:
    async def test_chama_transcribe_audio_url(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.transcribe_audio_url",
            new=AsyncMock(return_value="texto cru"),
        ) as m:
            r = await transcribe_audio.ainvoke({"audio_url": "https://x/a.ogg"})
            assert r == "texto cru"
            m.assert_awaited_once_with("https://x/a.ogg")

    async def test_falha_retorna_msg_erro(self):
        with patch(
            "whatsapp_langchain.agents.tools.midia.transcribe_audio_url",
            new=AsyncMock(side_effect=ValueError("audio inválido")),
        ):
            r = await transcribe_audio.ainvoke({"audio_url": "https://x/a.ogg"})
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
            r = await extract_document.ainvoke({"document_url": "https://x/d.pdf"})
            assert r == "Texto do PDF"
            # Confere que filename foi inferido como doc.pdf
            args, kwargs = m_ext.call_args
            assert args[0] == "doc.pdf"

    async def test_docx_filename(self):
        with (
            patch(
                "whatsapp_langchain.agents.tools.midia.download_media",
                new=AsyncMock(return_value=(b"PK\x03\x04...", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.extract_text",
                new=AsyncMock(return_value="Texto do DOCX"),
            ) as m_ext,
        ):
            await extract_document.ainvoke({"document_url": "https://x/c.docx"})
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
            r = await extract_document.ainvoke({"document_url": "https://x/d.pdf"})
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
            r = await extract_document.ainvoke({"document_url": "https://x/d.pdf"})
            assert "sem texto" in r


class TestSummarizeDocument:
    async def test_chama_extract_e_resume(self):
        # Mock: extract retorna texto, LLM retorna resumo
        async def fake_extract(_payload):
            return "Texto longo do documento"

        class FakeResp:
            content = "• Bullet 1\n• Bullet 2"

        with (
            patch.object(
                extract_document, "ainvoke",
                new=AsyncMock(return_value="Texto longo do documento"),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.create_chat_model",
            ) as m_llm,
        ):
            m_llm.return_value.ainvoke = AsyncMock(return_value=FakeResp())
            r = await summarize_document.ainvoke({"document_url": "https://x/d.pdf"})
            assert "Bullet 1" in r

    async def test_focus_propagado_no_prompt(self):
        class FakeResp:
            content = "resumo focado"

        captured_prompt = []

        async def captura(prompt):
            captured_prompt.append(prompt)
            return FakeResp()

        with (
            patch.object(
                extract_document, "ainvoke",
                new=AsyncMock(return_value="Conteúdo X"),
            ),
            patch(
                "whatsapp_langchain.agents.tools.midia.create_chat_model",
            ) as m_llm,
        ):
            m_llm.return_value.ainvoke = AsyncMock(side_effect=captura)
            await summarize_document.ainvoke(
                {"document_url": "https://x/d.pdf", "focus": "valor total"}
            )
            assert any("valor total" in p for p in captured_prompt)

    async def test_propaga_erro_da_extract(self):
        with patch.object(
            extract_document, "ainvoke",
            new=AsyncMock(return_value="[ERRO: download falhou]"),
        ):
            r = await summarize_document.ainvoke({"document_url": "https://x/d.pdf"})
            assert r.startswith("[ERRO")


# Marca todos como asyncio (conftest já configura asyncio_mode=auto)
pytestmark = pytest.mark.asyncio
