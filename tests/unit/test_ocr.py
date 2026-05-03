"""Tests do helper de OCR (M5.c.3)."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared import ocr


def _png_bytes(width: int = 100, height: int = 100, color="red") -> bytes:
    """Gera PNG válido em memória (PIL)."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- _resize_if_needed ---


def test_resize_keeps_small_image_intact():
    raw = _png_bytes(800, 600)
    out, mime = ocr._resize_if_needed(raw, "image/png")
    assert out == raw
    assert mime == "image/png"


def test_resize_shrinks_oversized_image():
    """Imagem acima de MAX_IMAGE_WIDTH_PX é redimensionada — checa dimensões."""
    from PIL import Image

    raw = _png_bytes(4000, 3000)
    out, mime = ocr._resize_if_needed(raw, "image/png")
    assert out != raw
    out_img = Image.open(io.BytesIO(out))
    assert out_img.width == ocr.MAX_IMAGE_WIDTH_PX
    assert mime in ("image/png", "image/jpeg")


def test_resize_invalid_image_raises():
    with pytest.raises(ocr.OCRError, match="imagem inválida"):
        ocr._resize_if_needed(b"not an image", "image/png")


# --- ocr_image_bytes ---


def _build_response(content: str = "Texto extraído da imagem"):
    response = MagicMock()
    response.json = MagicMock(
        return_value={"choices": [{"message": {"content": content}}]}
    )
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_ocr_image_returns_extracted_text():
    raw = _png_bytes()
    fake_response = _build_response("Texto da imagem")
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value.post = AsyncMock(return_value=fake_response)

    with (
        patch.object(ocr, "settings") as mock_settings,
        patch.object(ocr.httpx, "AsyncClient", return_value=fake_client),
    ):
        mock_settings.openrouter_api_key = MagicMock()
        mock_settings.openrouter_api_key.get_secret_value.return_value = "key"
        mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_settings.openrouter_midia_model = "google/gemini"
        out = await ocr.ocr_image_bytes(raw)
    assert out == "Texto da imagem"


@pytest.mark.asyncio
async def test_ocr_image_returns_empty_when_sem_texto():
    """LLM detectou ausência de texto — retorna string vazia."""
    raw = _png_bytes()
    fake_response = _build_response("[SEM TEXTO]")
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value.post = AsyncMock(return_value=fake_response)

    with (
        patch.object(ocr, "settings") as mock_settings,
        patch.object(ocr.httpx, "AsyncClient", return_value=fake_client),
    ):
        mock_settings.openrouter_api_key = MagicMock()
        mock_settings.openrouter_api_key.get_secret_value.return_value = "key"
        mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_settings.openrouter_midia_model = "google/gemini"
        out = await ocr.ocr_image_bytes(raw)
    assert out == ""


@pytest.mark.asyncio
async def test_ocr_image_handles_list_content():
    """Alguns modelos devolvem content como lista de blocos."""
    raw = _png_bytes()
    fake_response = _build_response(
        [{"type": "text", "text": "linha 1"}, {"type": "text", "text": "linha 2"}]
    )
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value.post = AsyncMock(return_value=fake_response)

    with (
        patch.object(ocr, "settings") as mock_settings,
        patch.object(ocr.httpx, "AsyncClient", return_value=fake_client),
    ):
        mock_settings.openrouter_api_key = MagicMock()
        mock_settings.openrouter_api_key.get_secret_value.return_value = "key"
        mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_settings.openrouter_midia_model = "google/gemini"
        out = await ocr.ocr_image_bytes(raw)
    assert "linha 1" in out
    assert "linha 2" in out


@pytest.mark.asyncio
async def test_ocr_image_raises_when_api_key_missing():
    raw = _png_bytes()
    with patch.object(ocr, "settings") as mock_settings:
        mock_settings.openrouter_api_key = None
        with pytest.raises(ocr.OCRError, match="OPENROUTER_API_KEY"):
            await ocr.ocr_image_bytes(raw)


@pytest.mark.asyncio
async def test_ocr_image_raises_on_http_error():
    raw = _png_bytes()
    import httpx as _httpx

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(
        side_effect=_httpx.HTTPError("500")
    )
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value.post = AsyncMock(return_value=fake_response)

    with (
        patch.object(ocr, "settings") as mock_settings,
        patch.object(ocr.httpx, "AsyncClient", return_value=fake_client),
    ):
        mock_settings.openrouter_api_key = MagicMock()
        mock_settings.openrouter_api_key.get_secret_value.return_value = "key"
        mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_settings.openrouter_midia_model = "google/gemini"
        with pytest.raises(ocr.OCRError, match="OpenRouter OCR falhou"):
            await ocr.ocr_image_bytes(raw)


# --- ocr_pdf_pages ---


@pytest.mark.asyncio
async def test_ocr_pdf_pages_joins_per_page():
    """Cada página é OCR-ed e juntadas com \\n\\n."""
    fake_pages = [MagicMock(), MagicMock()]
    for p in fake_pages:
        p.save = MagicMock()  # pdf2image PIL.Image.save

    with (
        patch("pdf2image.convert_from_bytes", return_value=fake_pages),
        patch.object(
            ocr,
            "ocr_image_bytes",
            AsyncMock(side_effect=["Página 1 texto", "Página 2 texto"]),
        ),
    ):
        out = await ocr.ocr_pdf_pages(b"%PDF-fake")
    assert "Página 1 texto" in out
    assert "Página 2 texto" in out
    assert "\n\n" in out


@pytest.mark.asyncio
async def test_ocr_pdf_pages_skips_empty_results():
    fake_pages = [MagicMock(), MagicMock()]
    for p in fake_pages:
        p.save = MagicMock()
    with (
        patch("pdf2image.convert_from_bytes", return_value=fake_pages),
        patch.object(
            ocr, "ocr_image_bytes", AsyncMock(side_effect=["", "valid"])
        ),
    ):
        out = await ocr.ocr_pdf_pages(b"%PDF-fake")
    assert out == "valid"


@pytest.mark.asyncio
async def test_ocr_pdf_pages_continues_after_page_failure():
    """Falha em 1 página não derruba todo o PDF."""
    fake_pages = [MagicMock(), MagicMock()]
    for p in fake_pages:
        p.save = MagicMock()
    with (
        patch("pdf2image.convert_from_bytes", return_value=fake_pages),
        patch.object(
            ocr,
            "ocr_image_bytes",
            AsyncMock(side_effect=[ocr.OCRError("flaky"), "page2"]),
        ),
    ):
        out = await ocr.ocr_pdf_pages(b"%PDF-fake")
    assert out == "page2"


@pytest.mark.asyncio
async def test_ocr_pdf_pages_rejects_when_too_many_pages():
    """PDF acima de MAX_PDF_PAGES → OCRError sem chamar OCR."""
    fake_pages = [MagicMock() for _ in range(ocr.MAX_PDF_PAGES + 1)]
    with (
        patch("pdf2image.convert_from_bytes", return_value=fake_pages),
        patch.object(ocr, "ocr_image_bytes", AsyncMock()) as mock_ocr,
    ):
        with pytest.raises(ocr.OCRError, match="máximo"):
            await ocr.ocr_pdf_pages(b"%PDF")
    mock_ocr.assert_not_called()


@pytest.mark.asyncio
async def test_ocr_pdf_pages_raises_when_pdf2image_fails():
    with patch(
        "pdf2image.convert_from_bytes", side_effect=Exception("poppler missing")
    ):
        with pytest.raises(ocr.OCRError, match="pdf2image"):
            await ocr.ocr_pdf_pages(b"corrupt")
