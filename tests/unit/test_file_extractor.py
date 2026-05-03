"""Tests do extractor de arquivos (M5.c.2)."""

import io

import pytest

from whatsapp_langchain.shared.file_extractor import (
    FileExtractionError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    detect_kind,
    extract_text,
)


# --- detect_kind ---


def test_detect_kind_pdf():
    assert detect_kind("manual.pdf") == "pdf"
    assert detect_kind("MANUAL.PDF") == "pdf"


def test_detect_kind_docx():
    assert detect_kind("contrato.docx") == "docx"


def test_detect_kind_md():
    assert detect_kind("readme.md") == "md"
    assert detect_kind("README.markdown") == "md"


def test_detect_kind_txt():
    assert detect_kind("notas.txt") == "txt"


def test_detect_kind_raises_on_unsupported():
    with pytest.raises(UnsupportedFileTypeError):
        detect_kind("imagem.bmp")
    with pytest.raises(UnsupportedFileTypeError):
        detect_kind("sem-extensao")
    with pytest.raises(UnsupportedFileTypeError):
        detect_kind("vid.mp4")


def test_detect_kind_image_extensions():
    """M5.c.3: png/jpg/jpeg/webp são suportados via OCR."""
    assert detect_kind("foto.png") == "image"
    assert detect_kind("scan.jpg") == "image"
    assert detect_kind("page.jpeg") == "image"
    assert detect_kind("doc.webp") == "image"


# --- extract_text TXT/MD ---


async def test_extract_txt_utf8():
    text = await extract_text("notas.txt", "Olá mundo, café.".encode("utf-8"))
    assert "Olá mundo" in text
    assert "café" in text


async def test_extract_md_preserves_markdown():
    md = "# Título\n\n- item 1\n- item 2"
    text = await extract_text("doc.md", md.encode("utf-8"))
    assert "# Título" in text
    assert "- item 1" in text


async def test_extract_txt_latin1_fallback():
    """Arquivos exportados de Excel/Word velho costumam vir em latin-1."""
    raw = "Resoluções e ações estratégicas".encode("latin-1")
    text = await extract_text("notas.txt", raw)
    assert "Resoluções" in text


# --- extract_text DOCX ---


def _build_docx(paragraphs: list[str]) -> bytes:
    """Helper: gera .docx em memória usando python-docx."""
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def test_extract_docx_returns_paragraphs():
    raw = _build_docx(["Política de trocas", "Prazo: 7 dias.", "Sem uso."])
    text = await extract_text("politica.docx", raw)
    assert "Política de trocas" in text
    assert "Prazo: 7 dias" in text
    assert "Sem uso" in text


async def test_extract_docx_empty_raises():
    raw = _build_docx([])
    with pytest.raises(FileExtractionError, match="nenhum texto"):
        await extract_text("vazio.docx", raw)


async def test_extract_docx_invalid_raises():
    with pytest.raises(FileExtractionError, match="DOCX inválido"):
        await extract_text("falso.docx", b"not a real docx")


# --- extract_text PDF ---


def _build_pdf(text: str) -> bytes:
    """Helper: gera PDF mínimo com texto via reportlab — fallback manual."""
    # Sem reportlab no projeto. Usar pypdf não cria — só lê. Vou usar
    # PdfWriter com uma página em branco e adicionar /Contents text...
    # Mais simples: criar PDF mínimo manualmente.
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length " + str(len(text) + 50).encode()
        + b">>\nstream\nBT /F1 12 Tf 50 700 Td ("
        + text.encode("ascii", errors="replace")
        + b") Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n"
        b"0000000055 00000 n\n0000000102 00000 n\n0000000180 00000 n\n"
        b"0000000300 00000 n\n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n400\n%%EOF\n"
    )
    return pdf


async def test_extract_pdf_returns_text():
    raw = _build_pdf("Politica de trocas em ate 7 dias.")
    # M5.c.3: texto < OCR_FALLBACK_MIN_CHARS aciona OCR. Aqui patch pra
    # desabilitar fallback e validar pypdf direto.
    from whatsapp_langchain.shared import file_extractor as fe

    monkey = pytest.MonkeyPatch()
    monkey.setattr(fe, "OCR_FALLBACK_MIN_CHARS", 0)
    try:
        text = await extract_text("policy.pdf", raw)
    finally:
        monkey.undo()
    assert "trocas" in text or "Politica" in text


@pytest.mark.asyncio
async def test_extract_pdf_falls_back_to_ocr_when_text_too_short():
    """M5.c.3: pypdf retorna pouco → chama _ocr_pdf."""
    from unittest.mock import AsyncMock, patch

    from whatsapp_langchain.shared import file_extractor as fe

    raw = _build_pdf("x")
    with patch.object(fe, "_ocr_pdf", AsyncMock(return_value="OCR EXTRAIU ISSO")):
        text = await extract_text("scan.pdf", raw)
    assert "OCR EXTRAIU ISSO" in text


@pytest.mark.asyncio
async def test_extract_image_calls_ocr():
    """M5.c.3: PNG é processado via OCR direto."""
    from unittest.mock import AsyncMock, patch

    from whatsapp_langchain.shared import file_extractor as fe

    fake_png = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    with patch.object(
        fe, "_ocr_image", AsyncMock(return_value="texto da imagem")
    ):
        text = await extract_text("foto.png", fake_png)
    assert "texto da imagem" in text


async def test_extract_pdf_invalid_raises():
    with pytest.raises(FileExtractionError, match="PDF inválido"):
        await extract_text("falso.pdf", b"not a pdf at all")


# --- size + content guards ---


async def test_extract_empty_bytes_raises():
    with pytest.raises(FileExtractionError, match="vazio"):
        await extract_text("x.txt", b"")


async def test_extract_too_large_raises():
    huge = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(FileTooLargeError):
        await extract_text("big.txt", huge)


async def test_extract_truncates_at_max_text_chars(monkeypatch):
    """Acima do limite, mantém só os primeiros MAX chars."""
    from whatsapp_langchain.shared import file_extractor

    monkeypatch.setattr(file_extractor, "MAX_TEXT_CHARS", 100)
    text = await extract_text("a.txt", ("x" * 500).encode())
    assert len(text) == 100


async def test_extract_unsupported_extension_raises():
    with pytest.raises(UnsupportedFileTypeError):
        await extract_text("video.mp4", b"fake video bytes")
