"""Output judge — Sprint O.4 (LLM-as-judge condicional).

Estratégia: NÃO valida toda resposta (custaria +1s sempre). Só roda quando:
  1. RAG não retornou hits fortes (top_score < 0.5 OU 0 hits)
  2. E resposta tem fatos verificáveis (números, datas, R$, %)
  3. E resposta NÃO é de "transferir/não sei"

Quando UNSAFE: registra em guardrail_log, retorna False (caller decide
ação — geralmente trocar pra "vou transferir pra atendente").

Cache TTL 1h por hash da resposta — evita reavaliar respostas repetidas.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

import structlog
from langchain_core.messages import HumanMessage

from whatsapp_langchain.shared.llm import create_chat_model

logger = structlog.get_logger()


JUDGE_MODEL = "openai/gpt-4o-mini"
JUDGE_CACHE_TTL = 3600  # 1h
RAG_SCORE_THRESHOLD = 0.5  # se top_score >= isso, skip judge (já ancorado)


# Cache: {hash → (verdict_bool, ts)}
_cache: dict[str, tuple[bool, float]] = {}


# Heurística: fatos verificáveis na resposta
_HAS_NUMBER_RE = re.compile(r"\b\d+([.,]\d+)?\b")
_HAS_MONEY_RE = re.compile(r"\bR\$\s*\d|\bUS\$\s*\d|\$\d", re.IGNORECASE)
_HAS_PERCENT_RE = re.compile(r"\d+\s*%")
_HAS_DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b"
    r"|\b(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b",
    re.IGNORECASE,
)
_HAS_TIME_RE = re.compile(r"\b\d{1,2}h\d{0,2}\b|\b\d{1,2}:\d{2}\b")
_TRANSFER_RE = re.compile(
    r"\b(transferir|atendente|n[ãa]o\s+(sei|tenho|posso)|n[ãa]o\s+consigo|pe[çc]o\s+desculpa)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JudgeResult:
    skipped: bool          # heurística decidiu não verificar
    safe: bool
    reason: str | None
    cached: bool


def _has_verifiable_facts(response: str) -> bool:
    """Resposta menciona algo concreto que poderia ser hallucination?"""
    return bool(
        _HAS_NUMBER_RE.search(response)
        or _HAS_MONEY_RE.search(response)
        or _HAS_PERCENT_RE.search(response)
        or _HAS_DATE_RE.search(response)
        or _HAS_TIME_RE.search(response)
    )


def _is_transfer_response(response: str) -> bool:
    """Resposta tipo 'vou transferir / não sei'?"""
    return bool(_TRANSFER_RE.search(response))


def should_judge(
    *, response: str, rag_top_score: float | None, rag_hits: int
) -> tuple[bool, str]:
    """Heurística pra decidir se precisa judge. Retorna (run_judge, motivo)."""
    if not response or len(response.strip()) < 20:
        return False, "response_too_short"
    if _is_transfer_response(response):
        return False, "transfer_response"
    if rag_hits > 0 and rag_top_score is not None and rag_top_score >= RAG_SCORE_THRESHOLD:
        return False, "rag_grounded"
    if not _has_verifiable_facts(response):
        return False, "no_verifiable_facts"
    return True, "rag_weak_with_facts"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:32]


async def judge_output(
    *,
    user_query: str,
    response: str,
    rag_context: str | None = None,
    rag_top_score: float | None = None,
    rag_hits: int = 0,
) -> JudgeResult:
    """Avalia se a resposta é segura (livre de hallucination grosseira).

    Retorna JudgeResult com:
      skipped=True: heurística pulou (sem custo de LLM)
      safe=True: aprovada
      safe=False: UNSAFE — caller deve trocar resposta por "vou transferir"
    """
    run, motivo = should_judge(
        response=response, rag_top_score=rag_top_score, rag_hits=rag_hits
    )
    if not run:
        return JudgeResult(skipped=True, safe=True, reason=motivo, cached=False)

    # Cache
    cache_key = _hash(f"{user_query}|||{response}")
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[1]) < JUDGE_CACHE_TTL:
        return JudgeResult(
            skipped=False, safe=cached[0], reason="cache_hit", cached=True
        )

    # Limpa cache se grande
    if len(_cache) > 500:
        for k in list(_cache.keys()):
            if (now - _cache[k][1]) > JUDGE_CACHE_TTL:
                del _cache[k]

    ctx_block = (
        f"Contexto disponível (base de conhecimento):\n{rag_context}\n\n"
        if rag_context else "Contexto disponível: nenhum (RAG vazio).\n\n"
    )

    prompt = f"""Você é um juiz que avalia se uma resposta de um agente de IA \
contém alegações INVENTADAS (hallucination) sobre fatos concretos \
(preços, prazos, percentuais, datas, políticas).

REGRAS:
- A resposta é SAFE se TODOS os fatos concretos podem ser justificados \
pelo contexto OU são afirmações genéricas (sem números específicos) OU \
afirmações verdadeiras universalmente.
- A resposta é UNSAFE se inventa preços/prazos/políticas que não estão \
no contexto.

Pergunta do cliente: {user_query[:300]}

{ctx_block}Resposta do agente: {response[:800]}

Responda APENAS uma palavra: SAFE ou UNSAFE"""

    try:
        llm = create_chat_model(model=JUDGE_MODEL, temperature=0.0, max_tokens=10)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        verdict = (
            result.content if isinstance(result.content, str)
            else str(result.content)
        ).strip().upper()
        safe = verdict.startswith("SAFE")
        _cache[cache_key] = (safe, now)
        if not safe:
            logger.warning(
                "guardrail_output_unsafe",
                response_preview=response[:200],
                rag_hits=rag_hits,
                rag_top_score=rag_top_score,
            )
        return JudgeResult(skipped=False, safe=safe, reason=verdict, cached=False)
    except Exception as e:
        logger.warning("judge_failed", error=str(e))
        # Falha do juiz: assume safe (não bloqueia atendimento por bug nosso)
        return JudgeResult(skipped=True, safe=True, reason=f"error:{e}", cached=False)
