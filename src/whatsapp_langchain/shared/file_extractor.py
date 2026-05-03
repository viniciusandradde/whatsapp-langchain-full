"""Extração de texto de arquivos enviados pra base de conhecimento.

M5.c.2: PDF, DOCX, MD, TXT.
M5.c.3: imagens diretas (PNG/JPG/JPEG/WebP) via OCR + fallback OCR
quando PDF retorna texto vazio (provavelmente escaneado).

Detecção é por extensão do nome (mais robusto que content-type que
browsers reportam de forma inconsistente).

Uso:
    text = await extract_text(filename, raw_bytes)

Levanta `UnsupportedFileTypeError` quando a extensão não bate com nenhum
parser conhecido, `FileExtractionError` quando o conteúdo não parseou,
`FileTooLargeError` quando excede o cap.
"""

from __future__ import annotations

import io
from pathlib import Path

import structlog

logger = structlog.get_logger()


# Cap de tamanho — evita estouro de memória com upload de arquivo enorme.
# 10 MB cobre PDFs e docx de manuais; uploads maiores que isso devem ser
# divididos pelo admin.
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Tamanho máximo razoável de texto extraído. Acima disso o RAG fica caro
# pra reindexar e o admin provavelmente colou doc errado.
MAX_TEXT_CHARS = 200_000

# PDF com texto extraído menor que isso → cai no fallback OCR (M5.c.3).
# 50 chars cobre PDFs escaneados onde pypdf retorna metadata residual.
OCR_FALLBACK_MIN_CHARS = 50


SUPPORTED_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".md",
    ".markdown",
    ".txt",
    # M5.c.3: imagens via OCR
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)


_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class UnsupportedFileTypeError(ValueError):
    """Extensão fora de SUPPORTED_EXTENSIONS."""


class FileExtractionError(ValueError):
    """Falha ao extrair texto (PDF quebrado, docx vazio, etc)."""


class FileTooLargeError(ValueError):
    """Arquivo excedeu MAX_FILE_SIZE_BYTES."""


def detect_kind(filename: str) -> str:
    """Retorna `pdf` | `docx` | `md` | `txt` | `image`. Levanta se não suportado."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in (".md", ".markdown"):
        return "md"
    if ext == ".txt":
        return "txt"
    if ext in _IMAGE_MIME_BY_EXT:
        return "image"
    raise UnsupportedFileTypeError(
        f"extensão {ext or '<sem extensão>'} não suportada — "
        f"aceitos: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


async def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Extrai texto plain do arquivo. Limpa whitespace excessivo no fim.

    M5.c.3: virou async porque PDF escaneado e imagens caem no OCR
    (Vision LLM async). MD/TXT/DOCX continuam sync internamente.
    """
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"arquivo tem {len(raw_bytes)} bytes — máximo é "
            f"{MAX_FILE_SIZE_BYTES}"
        )
    if not raw_bytes:
        raise FileExtractionError("arquivo vazio")

    kind = detect_kind(filename)
    used_ocr = False
    if kind == "pdf":
        text = _extract_pdf(raw_bytes)
        if len(text) < OCR_FALLBACK_MIN_CHARS:
            logger.info(
                "file_extractor_pdf_ocr_fallback",
                filename=filename,
                pypdf_chars=len(text),
            )
            text = await _ocr_pdf(raw_bytes)
            used_ocr = True
    elif kind == "docx":
        text = _extract_docx(raw_bytes)
    elif kind in ("md", "txt"):
        text = _extract_text_plain(raw_bytes)
    elif kind == "image":
        text = await _ocr_image(filename, raw_bytes)
        used_ocr = True
    else:  # pragma: no cover — detect_kind teria levantado
        raise UnsupportedFileTypeError(kind)

    text = _clean_whitespace(text)
    if not text:
        raise FileExtractionError(
            f"nenhum texto extraído de {filename!r} — "
            "OCR não detectou texto legível ou arquivo corrompido."
        )
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        logger.warning(
            "file_extraction_truncated",
            filename=filename,
            kind=kind,
            chars_kept=MAX_TEXT_CHARS,
        )
    logger.info(
        "file_extracted",
        filename=filename,
        kind=kind,
        bytes_in=len(raw_bytes),
        chars_out=len(text),
        used_ocr=used_ocr,
    )
    return text


def _extract_pdf(raw: bytes) -> str:
    from pypdf import PdfReader  # lazy import — só carrega se usuario subir PDF

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as e:
        raise FileExtractionError(f"PDF inválido: {e}") from e

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:
            logger.warning("pdf_page_extract_failed", error=str(e))
    return "\n\n".join(p.strip() for p in parts if p.strip())


async def _ocr_pdf(raw: bytes) -> str:
    """Fallback pra PDFs escaneados — chama OCR via Vision LLM."""
    from whatsapp_langchain.shared.ocr import OCRError, ocr_pdf_pages

    try:
        return await ocr_pdf_pages(raw)
    except OCRError as e:
        raise FileExtractionError(f"OCR do PDF falhou: {e}") from e


async def _ocr_image(filename: str, raw: bytes) -> str:
    """OCR direto de upload PNG/JPG/JPEG/WebP."""
    from whatsapp_langchain.shared.ocr import OCRError, ocr_image_bytes

    ext = Path(filename).suffix.lower()
    mime = _IMAGE_MIME_BY_EXT.get(ext, "image/png")
    try:
        return await ocr_image_bytes(raw, mime_type=mime)
    except OCRError as e:
        raise FileExtractionError(f"OCR da imagem falhou: {e}") from e


def _extract_docx(raw: bytes) -> str:
    from docx import Document  # lazy import

    try:
        doc = Document(io.BytesIO(raw))
    except Exception as e:
        raise FileExtractionError(f"DOCX inválido: {e}") from e

    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_text_plain(raw: bytes) -> str:
    """MD/TXT: tenta UTF-8, cai pra latin-1 se falhar (pt-BR comum)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1")
        except UnicodeDecodeError as e:
            raise FileExtractionError(
                f"não consegui decodificar texto: {e}"
            ) from e


def _clean_whitespace(text: str) -> str:
    """Colapsa espaços/linhas excessivas que pdf parser costuma deixar."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    blank_streak = 0
    for line in lines:
        if not line:
            blank_streak += 1
            if blank_streak <= 2:
                out.append("")
        else:
            blank_streak = 0
            out.append(line)
    return "\n".join(out).strip()
