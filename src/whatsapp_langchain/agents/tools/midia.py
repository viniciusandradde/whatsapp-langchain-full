"""Tools multimodais pro agente — Atendimento Completo.

4 tools que permitem ao agente reanalisar mídia ON-DEMAND, depois do
pré-processamento automático do worker:

- analyze_image(focus?) — re-análise focada em pergunta
- transcribe_audio() — transcrição literal
- extract_document() — texto cru de PDF/DOCX
- summarize_document(focus?) — resumo executivo

A `media_url` real do anexo do turno é injetada via `RunnableConfig`
(LangGraph runtime) — agente NÃO recebe URL como parâmetro (evita
alucinação de URL inventada). Worker passa em
`invoke_config["configurable"]["media_url"]` quando há mídia.

Use as tools quando descrição/transcrição/extração inicial perdeu detalhe
específico ou documento é muito longo. Se o input já contém
`[Conteúdo do documento]:` / `[Descrição de imagem]:` /
`[Transcrição de áudio]:`, leia primeiro e responda direto SEM chamar tool.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared.file_extractor import extract_text
from whatsapp_langchain.shared.llm import create_chat_model
from whatsapp_langchain.shared.midia_processing import (
    chat_completion_media,
    describe_image_url,
    download_media,
    transcribe_audio_url,
)

logger = structlog.get_logger()

_MAX_DOC_CHARS = 30_000
_MAX_FOCUS_CHARS = 500


def _extract_runtime_config(runtime: Any) -> dict[str, Any]:
    """Lê configurable do RunnableConfig — mesmo padrão de cliente_atendimento."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict):
                return cfg
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable
    return {}


def _get_media_url(runtime: Any) -> str | None:
    """Retorna media_url do turno atual via RunnableConfig.

    Worker injeta em invoke_config["configurable"]["media_url"] quando
    message.media_url está presente. None = não há mídia anexada.
    """
    cfg = _extract_runtime_config(runtime)
    media_url = cfg.get("media_url")
    return media_url if isinstance(media_url, str) and media_url else None


@tool
async def analyze_image(
    focus: str | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Reanalisa a imagem que o cliente acabou de enviar com pergunta direcionada.

    Use APENAS quando a `[Descrição de imagem]:` que veio no input não
    respondeu o que você precisa — ex: cliente mandou screenshot de erro
    pedindo ajuda com detalhe que a descrição genérica não capturou.

    Args:
        focus: pergunta direcionada (ex: "qual o número do pedido visível?",
               "leia o texto da etiqueta"). Sem focus, faz descrição geral.

    Retorna texto puro com a resposta. Se não há imagem anexada nesse turno,
    retorna mensagem de erro — nesse caso responda ao cliente que precisa
    da imagem reenviada.
    """
    media_url = _get_media_url(runtime)
    if not media_url:
        return "[ERRO: Nenhuma imagem anexada nesse turno do cliente.]"
    try:
        return await describe_image_url(media_url, focus=focus)
    except Exception as exc:
        logger.warning("analyze_image_failed", error=str(exc))
        return f"[ERRO: não consegui re-analisar a imagem — {exc!s:.200}]"


@tool
async def transcribe_audio(
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Re-transcreve o áudio do cliente literalmente em pt-BR.

    Use APENAS quando a `[Transcrição de áudio]:` que veio no input teve
    trecho ininteligível ou termo técnico errado, ou quando precisa do
    conteúdo cru pra citar literalmente.
    """
    media_url = _get_media_url(runtime)
    if not media_url:
        return "[ERRO: Nenhum áudio anexado nesse turno.]"
    try:
        return await transcribe_audio_url(media_url)
    except Exception as exc:
        logger.warning("transcribe_audio_failed", error=str(exc))
        return f"[ERRO: não consegui re-transcrever o áudio — {exc!s:.200}]"


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
        ext = ct.split("/")[1].split(";")[0] or "jpg"
        return f"doc.{ext}"
    return fallback


@tool
async def extract_document(
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Extrai texto completo do documento (PDF/DOCX) que o cliente enviou.

    Use APENAS quando o `[Conteúdo do documento (...)]:` que veio no input
    foi truncado E você precisa de trecho específico não capturado nos
    primeiros 10k chars. Pra documentos pequenos, leia direto do input.

    Tenta extração nativa (`pypdf`/`python-docx`); cai pra OCR via Vision
    OpenRouter se documento for escaneado. Limite ~30k chars (truncado).
    """
    media_url = _get_media_url(runtime)
    if not media_url:
        return "[ERRO: Nenhum documento anexado nesse turno.]"
    try:
        body, ctype = await download_media(media_url)
        filename = _filename_from_ctype(ctype)
        text = await extract_text(filename, body)
        if not text:
            return "[Documento sem texto extraível.]"
        if len(text) > _MAX_DOC_CHARS:
            return text[:_MAX_DOC_CHARS] + f"\n\n[...truncado em {_MAX_DOC_CHARS} chars]"
        return text
    except Exception as exc:
        logger.warning("extract_document_failed", error=str(exc))
        return f"[ERRO: não consegui extrair o documento — {exc!s:.200}]"


@tool
async def summarize_document(
    focus: str | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Resume o documento enviado pelo cliente em até 5 bullets.

    Use APENAS quando o documento é longo (>5 páginas) ou cliente pediu
    resumo direto. Pra docs curtos, leia o `[Conteúdo do documento]:`
    direto do input e responda baseado nele.

    Args:
        focus: tópico que deve receber atenção especial (opcional).
               Ex: "cláusula de cancelamento", "valor total", "data de vencimento".
    """
    media_url = _get_media_url(runtime)
    if not media_url:
        return "[ERRO: Nenhum documento anexado nesse turno.]"

    raw = await extract_document.ainvoke({}, config={"configurable": {"media_url": media_url}})
    if raw.startswith("[ERRO") or raw.startswith("[Documento"):
        return raw
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
        logger.warning("summarize_document_failed", error=str(exc))
        return f"[ERRO: não consegui resumir o documento — {exc!s:.200}]"


__all__ = [
    "analyze_image",
    "transcribe_audio",
    "extract_document",
    "summarize_document",
    "chat_completion_media",
]
