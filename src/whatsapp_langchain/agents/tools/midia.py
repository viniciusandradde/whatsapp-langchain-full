"""Tools multimodais pro agente — Atendimento Completo.

4 tools que permitem ao agente reanalisar mídia ON-DEMAND, depois do
pré-processamento automático do worker:

- analyze_image(image_url, focus?) — re-análise focada em pergunta
- transcribe_audio(audio_url) — transcrição literal
- extract_document(document_url) — texto cru de PDF/DOCX
- summarize_document(document_url, focus?) — resumo executivo

Use quando descrição/transcrição inicial perdeu detalhe específico ou
documento é muito longo.
"""

from __future__ import annotations

import structlog
from langchain_core.tools import tool

from whatsapp_langchain.shared.file_extractor import extract_text
from whatsapp_langchain.shared.llm import create_chat_model
from whatsapp_langchain.shared.midia_processing import (
    chat_completion_media,
    describe_image_url,
    download_media,
    transcribe_audio_url,
)

logger = structlog.get_logger()

_MAX_DOC_CHARS = 30_000  # ~10-15 páginas; truncamento defensivo
_MAX_FOCUS_CHARS = 500


@tool
async def analyze_image(image_url: str, focus: str | None = None) -> str:
    """Reanalisa uma imagem fazendo pergunta específica.

    Use quando descrição inicial não respondeu o que você precisa, OU
    quando o cliente mandou screenshot/foto pedindo ajuda com detalhe
    técnico (botão errado, mensagem de erro, código de barras, número de
    pedido, etiqueta de produto, parcela do contrato).

    Args:
        image_url: URL da imagem (vem em `media_url` da mensagem original).
        focus: Pergunta direcionada (ex: "qual o número do pedido visível?",
               "leia o texto da etiqueta"). Sem focus, faz descrição geral.

    Retorna texto puro com a resposta — sem markdown, sem preâmbulo.
    """
    try:
        return await describe_image_url(image_url, focus=focus)
    except Exception as exc:
        logger.warning("analyze_image_failed", url=image_url, error=str(exc))
        return f"[ERRO: não consegui analisar a imagem — {exc!s:.200}]"


@tool
async def transcribe_audio(audio_url: str) -> str:
    """Re-transcreve áudio do cliente literalmente em pt-BR.

    Use quando primeira transcrição (que já vem no input) teve trecho
    ininteligível, termo técnico errado, ou quando precisa do conteúdo
    cru pra citar literalmente (ex: "exatamente o que ele disse?").

    Args:
        audio_url: URL do áudio (vem em `media_url` da mensagem original).
    """
    try:
        return await transcribe_audio_url(audio_url)
    except Exception as exc:
        logger.warning("transcribe_audio_failed", url=audio_url, error=str(exc))
        return f"[ERRO: não consegui transcrever o áudio — {exc!s:.200}]"


def _filename_from_ctype(content_type: str | None, fallback: str = "doc.pdf") -> str:
    """Infere filename a partir do content-type pra `extract_text` decidir parser."""
    if not content_type:
        return fallback
    ct = content_type.lower()
    if "pdf" in ct:
        return "doc.pdf"
    if "wordprocessingml" in ct or "docx" in ct:
        return "doc.docx"
    if "msword" in ct:
        return "doc.doc"
    if ct.startswith("text/"):
        return "doc.txt"
    if "image/" in ct:
        # imagem-de-doc → OCR via fluxo de imagem
        ext = ct.split("/")[1].split(";")[0] or "jpg"
        return f"doc.{ext}"
    return fallback


@tool
async def extract_document(document_url: str) -> str:
    """Extrai texto completo de PDF/DOCX/imagem-de-documento enviado.

    Tenta extração nativa (`pypdf`/`python-docx`); cai pra OCR via Vision
    OpenRouter se documento for escaneado/imagem. Limite: ~30 mil caracteres
    (truncado com aviso).

    Use pra docs do cliente: comprovante, contrato, manual, RG/CPF,
    boleto, orçamento, planilha simples.

    Args:
        document_url: URL do documento (vem em `media_url` da mensagem).
    """
    try:
        body, ctype = await download_media(document_url)
        filename = _filename_from_ctype(ctype)
        text = await extract_text(filename, body)
        if not text:
            return "[Documento sem texto extraível.]"
        if len(text) > _MAX_DOC_CHARS:
            return text[:_MAX_DOC_CHARS] + f"\n\n[...truncado em {_MAX_DOC_CHARS} chars]"
        return text
    except Exception as exc:
        logger.warning("extract_document_failed", url=document_url, error=str(exc))
        return f"[ERRO: não consegui extrair o documento — {exc!s:.200}]"


@tool
async def summarize_document(document_url: str, focus: str | None = None) -> str:
    """Extrai e resume documento em até 5 bullets.

    Use pra docs longos (contratos, comprovantes detalhados, manuais,
    relatórios). Se `focus` fornecido (ex: "cláusula de cancelamento",
    "valor total", "data de vencimento"), prioriza esse tópico no resumo.

    Args:
        document_url: URL do documento.
        focus: tópico que deve receber atenção especial (opcional).
    """
    raw = await extract_document.ainvoke({"document_url": document_url})
    if raw.startswith("[ERRO") or raw.startswith("[Documento"):
        return raw  # propaga erro
    focus_clean = (focus or "").strip()[:_MAX_FOCUS_CHARS]
    instr = (
        "Resuma o documento abaixo em PORTUGUÊS BRASILEIRO em até 5 bullets curtos. "
        "Não invente — só extraia o que está no texto. "
    )
    if focus_clean:
        instr += (
            f"Priorize informação sobre: '{focus_clean}'. Se o tópico não aparecer, "
            "diga 'tópico não mencionado no documento' e faça resumo geral. "
        )
    instr += "\n\n--- DOCUMENTO ---\n" + raw
    try:
        llm = create_chat_model()
        resp = await llm.ainvoke(instr)
        return str(resp.content).strip()
    except Exception as exc:
        logger.warning("summarize_document_failed", url=document_url, error=str(exc))
        return f"[ERRO: não consegui resumir o documento — {exc!s:.200}]"


# chat_completion_media re-exportado pra eventual uso externo
__all__ = [
    "analyze_image",
    "transcribe_audio",
    "extract_document",
    "summarize_document",
    "chat_completion_media",
]
