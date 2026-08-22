"""Extração de texto de arquivos enviados pra base de conhecimento.

M5.c.2: PDF, DOCX, MD, TXT.
M5.c.3: imagens diretas (PNG/JPG/JPEG/WebP) via OCR + fallback OCR
quando PDF retorna texto vazio (provavelmente escaneado).
2026-08-05: XLSX (openpyxl) e DOC legado (antiword), para o agente ler o que o
cliente manda pelo WhatsApp — ver `worker/media.py`.

Detecção é por extensão do nome (mais robusto que content-type que
browsers reportam de forma inconsistente).

Uso:
    text = await extract_text(filename, raw_bytes)

Levanta `UnsupportedFileTypeError` quando a extensão não bate com nenhum
parser conhecido, `FileExtractionError` quando o conteúdo não parseou,
`FileTooLargeError` quando excede o cap.
"""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
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
    # Word 97–2003. Depende do binário `antiword` (apt) — quando ele falta, a
    # extração levanta UnsupportedFileTypeError e o chamador degrada para
    # "recebi seu arquivo" em vez de erro. Ver `_extract_doc`.
    ".doc",
    # Planilha. `_media_kind` já classificava xlsx como documento, mas o nome
    # inferido caía em `doc.bin` e era recusado aqui — foi o defeito do
    # atendimento 1018-000664.
    ".xlsx",
    ".md",
    ".markdown",
    ".txt",
    # M5.c.3: imagens via OCR
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)

# Teto de linhas por aba na planilha. Sem isto uma base de 50 mil linhas
# estoura MAX_TEXT_CHARS no meio da primeira aba e as outras somem sem aviso.
MAX_XLSX_ROWS_POR_ABA = 500


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
    """Retorna `pdf` | `docx` | `doc` | `xlsx` | `md` | `txt` | `image`.

    Levanta `UnsupportedFileTypeError` se a extensão não tem parser.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext == ".doc":
        return "doc"
    if ext == ".xlsx":
        return "xlsx"
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


# mime → nome de arquivo plausível, para quando o remetente não mandou o nome.
#
# Fonte única de propósito: até 2026-08-05 esta tabela existia copiada em
# `worker/media.py` e em `agents/tools/midia.py`, e as duas cópias mandavam
# planilha para `doc.bin` — que `detect_kind` recusa. O cliente recebia "estamos
# com dificuldades em processar imagens/audio" por causa de um `.bin` inventado
# aqui dentro. Ordem importa: `wordprocessingml` antes de `openxmlformats`.
_NOME_POR_MIME: tuple[tuple[str, str], ...] = (
    ("pdf", "doc.pdf"),
    ("wordprocessingml", "doc.docx"),
    ("docx", "doc.docx"),
    ("spreadsheetml", "doc.xlsx"),
    ("ms-excel", "doc.xls"),
    ("msword", "doc.doc"),
)


def filename_for_media_type(media_type: str | None, fallback: str = "doc.bin") -> str:
    """Nome de arquivo inferido do mime, para payload que não traz o nome.

    Só serve de rede de segurança: quando o provedor manda o nome real
    (`documentMessage.fileName` no Evolution, `document.filename` no WABA), é o
    nome real que deve chegar aqui — ele é mais confiável que o mime e é o que
    o cliente vê.
    """
    mt = (media_type or "").lower()
    if not mt:
        return fallback
    for chave, nome in _NOME_POR_MIME:
        if chave in mt:
            return nome
    if mt.startswith("text/"):
        return "doc.txt"
    if mt.startswith("image/"):
        ext = mt.split("/", 1)[1].split(";")[0].strip() or "jpg"
        return f"doc.{ext}"
    return fallback


async def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Extrai texto plain do arquivo. Limpa whitespace excessivo no fim.

    M5.c.3: virou async porque PDF escaneado e imagens caem no OCR
    (Vision LLM async). MD/TXT/DOCX continuam sync internamente.
    """
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"arquivo tem {len(raw_bytes)} bytes — máximo é {MAX_FILE_SIZE_BYTES}"
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
    elif kind == "doc":
        text = await _extract_doc(raw_bytes)
    elif kind == "xlsx":
        text = _extract_xlsx(raw_bytes)
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


async def _extract_doc(raw: bytes) -> str:
    """Word 97–2003 (`.doc`) via `antiword`, instalado por apt na imagem.

    Formato binário OLE — não há parser puro-Python confiável, e o `.docx` do
    `python-docx` não serve. Quando o binário não está na imagem, levanta
    `UnsupportedFileTypeError` de propósito: o chamador trata isso como "não sei
    ler este arquivo" e confirma o recebimento pelo nome, que é melhor para o
    cliente do que um erro.

    Subprocesso assíncrono para não travar o loop do worker enquanto o antiword
    roda.
    """
    exe = shutil.which("antiword")
    if exe is None:
        raise UnsupportedFileTypeError(
            "leitura de .doc indisponível nesta instalação (antiword ausente)"
        )

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        proc = await asyncio.create_subprocess_exec(
            exe,
            "-w",
            "0",  # sem quebra de linha artificial: o texto vem em parágrafos
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError as e:
            proc.kill()
            raise FileExtractionError("antiword excedeu 30s") from e
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        detalhe = stderr.decode("utf-8", errors="replace").strip()[:200]
        raise FileExtractionError(f"antiword falhou ({proc.returncode}): {detalhe}")

    try:
        return stdout.decode("utf-8")
    except UnicodeDecodeError:
        # antiword sem `-m` usa o mapeamento padrão (latin-1 em pt-BR).
        return stdout.decode("latin-1", errors="replace")


def _extract_xlsx(raw: bytes) -> str:
    """Planilha como texto: uma seção por aba, células separadas por tabulação.

    `data_only=True` entrega o valor calculado em vez da fórmula — é o que o
    agente precisa ler. `read_only=True` evita carregar a planilha inteira em
    memória.
    """
    from openpyxl import load_workbook  # lazy import

    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:
        raise FileExtractionError(f"XLSX inválido: {e}") from e

    partes: list[str] = []
    try:
        for ws in wb.worksheets:
            linhas: list[str] = []
            truncou = False
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= MAX_XLSX_ROWS_POR_ABA:
                    truncou = True
                    break
                celulas = ["" if c is None else str(c).strip() for c in row]
                if not any(celulas):
                    continue
                linhas.append("\t".join(celulas).rstrip("\t"))
            if truncou:
                linhas.append(f"[... aba truncada em {MAX_XLSX_ROWS_POR_ABA} linhas]")
            if linhas:
                partes.append(f"[Aba: {ws.title}]\n" + "\n".join(linhas))
    finally:
        wb.close()

    return "\n\n".join(partes)


def _extract_text_plain(raw: bytes) -> str:
    """MD/TXT: tenta UTF-8, cai pra latin-1 se falhar (pt-BR comum)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1")
        except UnicodeDecodeError as e:
            raise FileExtractionError(f"não consegui decodificar texto: {e}") from e


def _clean_whitespace(text: str) -> str:
    """Colapsa espaços/linhas excessivas que pdf parser costuma deixar.

    Também remove **NUL (0x00)**, que não é whitespace mas mata o fluxo do mesmo
    jeito: o Postgres recusa NUL em campo `text`, e um PDF real de produção
    ("Rosa Maria 2 18-08.pdf", 2026-08-21) extraiu 11 mil caracteres com sucesso
    para depois derrubar o worker cinco vezes com `DataError` na hora de gravar.
    O cliente ficou sem resposta por um byte invisível.

    A limpeza fica aqui porque este é o funil por onde passam PDF, DOCX, XLSX e
    DOC — corrigir no gravador resolveria um caminho e deixaria os outros.
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
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
