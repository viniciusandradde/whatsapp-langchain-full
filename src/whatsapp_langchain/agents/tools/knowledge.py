"""Tool de busca na base de conhecimento da empresa (M5.c).

Injetada no agente apenas quando a empresa tem ≥1 documento ativo
(`has_active_documents` no loader). Usa cosine similarity via pgvector
e retorna top-3 docs com snippet pra o agente usar como contexto.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared import base_conhecimento
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def _extract_empresa_id(runtime: Any) -> int | None:
    """Lê `empresa_id` do contexto LangGraph (igual ao calendar tool)."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict) and "empresa_id" in cfg:
                return int(cfg["empresa_id"])
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict) and "empresa_id" in configurable:
            return int(configurable["empresa_id"])
    return None


def _snippet(texto: str, max_chars: int = 400) -> str:
    """Recorta o conteúdo pra não estourar o contexto do modelo."""
    texto = texto.strip()
    if len(texto) <= max_chars:
        return texto
    return texto[: max_chars - 1].rstrip() + "…"


@tool
async def search_knowledge_base(
    query: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Busca na base de conhecimento da empresa (FAQs, políticas, scripts).

    Use SEMPRE antes de responder perguntas factuais sobre produto, política
    ou processo da empresa — a base contém respostas pré-aprovadas que devem
    ser preferidas a respostas genéricas. Argumento:
    - query: pergunta do cliente (use as palavras dele, sem reformular).

    Retorna até 3 trechos relevantes com título. Se nada for encontrado,
    informa explicitamente — nesse caso responda com cuidado, sem inventar.
    """
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return "empresa_id ausente no contexto — não consigo consultar a base."
    pool = await get_pool()
    try:
        results = await base_conhecimento.search_relevant(
            pool, empresa_id, query
        )
    except Exception as e:
        logger.warning("knowledge_search_failed", error=str(e))
        return f"Não consegui consultar a base de conhecimento agora: {e}"

    logger.info(
        "knowledge_search",
        empresa_id=empresa_id,
        query_chars=len(query),
        hits=len(results),
    )
    if not results:
        return "Nenhum documento relevante encontrado na base de conhecimento."

    # M5.c.1: cita doc_id + chunk_idx no contexto pra o agente referenciar
    # corretamente ("conforme o doc 12 trecho 3, ..."). Inclui reason
    # do reranker quando disponível.
    lines: list[str] = []
    for r in results:
        meta = (
            f"doc {r.documento.id}, trecho {r.chunk_idx}, "
            f"relevância {r.score:.2f}"
        )
        if r.reason:
            meta += f" — {r.reason}"
        lines.append(f"- [{r.documento.titulo}] ({meta})\n  {_snippet(r.chunk_conteudo)}")
    return "Trechos relevantes da base de conhecimento:\n" + "\n".join(lines)
