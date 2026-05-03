"""Extração de texto de arquivos enviados pra base de conhecimento (M5.c.2).

Suporta PDF, DOCX, MD e TXT. Detecção por extensão do nome (mais robusto
que content-type que browsers reportam de forma inconsistente).

Uso:
    text = extract_text(filename, raw_bytes)

Levanta `UnsupportedFileTypeError` quando a extensão não bate com nenhum
parser conhecido. Levanta `FileExtractionError` quando o conteúdo não
parseou (PDF corrompido, .docx vazio, etc).
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


SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".md", ".markdown", ".txt")


class UnsupportedFileTypeError(ValueError):
    """Extensão fora de SUPPORTED_EXTENSIONS."""


class FileExtractionError(ValueError):
    """Falha ao extrair texto (PDF quebrado, docx vazio, etc)."""


class FileTooLargeError(ValueError):
    """Arquivo excedeu MAX_FILE_SIZE_BYTES."""


def detect_kind(filename: str) -> str:
    """Retorna `pdf` | `docx` | `md` | `txt`. Levanta se não suportado."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in (".md", ".markdown"):
        return "md"
    if ext == ".txt":
        return "txt"
    raise UnsupportedFileTypeError(
        f"extensão {ext or '<sem extensão>'} não suportada — "
        f"aceitos: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Extrai texto plain do arquivo. Limpa whitespace excessivo no fim."""
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"arquivo tem {len(raw_bytes)} bytes — máximo é "
            f"{MAX_FILE_SIZE_BYTES}"
        )
    if not raw_bytes:
        raise FileExtractionError("arquivo vazio")

    kind = detect_kind(filename)
    if kind == "pdf":
        text = _extract_pdf(raw_bytes)
    elif kind == "docx":
        text = _extract_docx(raw_bytes)
    elif kind == "md":
        text = _extract_text_plain(raw_bytes)
    elif kind == "txt":
        text = _extract_text_plain(raw_bytes)
    else:  # pragma: no cover — detect_kind teria levantado
        raise UnsupportedFileTypeError(kind)

    text = _clean_whitespace(text)
    if not text:
        raise FileExtractionError(
            f"nenhum texto extraído de {filename!r} — arquivo escaneado "
            "sem OCR? formato corrompido?"
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
    # Remove linhas só com espaços em branco
    lines = [line.rstrip() for line in text.splitlines()]
    # Reduz sequências de 3+ linhas em branco para no máximo 2 (limite de parágrafo).
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
