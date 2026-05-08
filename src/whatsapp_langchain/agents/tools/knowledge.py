"""Tool de busca na base de conhecimento da empresa (M5.c).

Injetada no agente apenas quando a empresa tem ≥1 documento ativo
(`has_active_documents` no loader). Usa cosine similarity via pgvector
e retorna top-3 docs com snippet pra o agente usar como contexto.
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared import base_conhecimento
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def _extract_from_runtime(runtime: Any, key: str) -> Any:
    """Lê uma chave do `configurable` do contexto LangGraph."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict) and key in cfg:
                return cfg[key]
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict) and key in configurable:
            return configurable[key]
    return None


def _extract_empresa_id(runtime: Any) -> int | None:
    val = _extract_from_runtime(runtime, "empresa_id")
    return int(val) if val is not None else None


def _extract_pasta_ids(runtime: Any) -> list[int] | None:
    """Lê `base_conhecimento_ids` do contexto (Sprint M).

    Setor-específico: agente_ia.base_conhecimento_ids define quais pastas
    a tool deve consultar. Vazio/None → busca em toda a empresa (fallback).
    """
    val = _extract_from_runtime(runtime, "base_conhecimento_ids")
    if val is None:
        return None
    try:
        ids = [int(x) for x in val if x is not None]
        return ids if ids else None
    except (TypeError, ValueError):
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
    pasta_ids = _extract_pasta_ids(runtime)
    agente_slug = _extract_from_runtime(runtime, "agent_id") or _extract_from_runtime(runtime, "agente_slug")
    atendimento_id = _extract_from_runtime(runtime, "atendimento_id")
    thread_id = _extract_from_runtime(runtime, "thread_id")
    pool = await get_pool()
    started = time.perf_counter()
    error_msg: str | None = None
    results: list = []
    try:
        results = await base_conhecimento.search_relevant(
            pool, empresa_id, query, pasta_ids=pasta_ids
        )
    except Exception as e:
        error_msg = str(e)[:500]
        logger.warning("knowledge_search_failed", error=error_msg)

    duracao_ms = int((time.perf_counter() - started) * 1000)
    top_score = float(results[0].score) if results else None

    # Persiste log pra dashboard (best-effort — não bloqueia resposta)
    with suppress(Exception):
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO rag_query_log (
                    empresa_id, query_text, pasta_ids, agente_slug,
                    atendimento_id, thread_id, hits, top_score,
                    duracao_ms, error
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    empresa_id,
                    query[:500],
                    list(pasta_ids or []),
                    agente_slug,
                    int(atendimento_id) if atendimento_id else None,
                    thread_id,
                    len(results),
                    top_score,
                    duracao_ms,
                    error_msg,
                ),
            )
            await conn.commit()

    if error_msg:
        return f"Não consegui consultar a base de conhecimento agora: {error_msg}"

    logger.info(
        "knowledge_search",
        empresa_id=empresa_id,
        pasta_ids=pasta_ids,
        query_chars=len(query),
        hits=len(results),
        duracao_ms=duracao_ms,
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
