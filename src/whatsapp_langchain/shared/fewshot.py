"""Few-shot retrieval — injeta exemplos passados validados no system prompt
do agente (Sprint P.3).

Pipeline:
1. Cliente manda mensagem
2. Antes do agente rodar, busca top-K exemplos similares por embedding
3. Filtra: mesmo agente_slug, status=ready, outcome=success
4. Formata como bloco "EXEMPLOS DE RESPOSTAS QUE FUNCIONARAM" no prompt

Backfill: quando atendimento muda pra outcome=success, extrai pares
(cliente_msg, agente_resposta) das mensagens e popula fewshot_example.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.base_conhecimento import (
    _embed,
    _vector_literal,
)

logger = structlog.get_logger()


FEWSHOT_TOP_K = 3
FEWSHOT_MIN_SIMILARITY = 0.65


async def find_similar_examples(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    agente_slug: str,
    query: str,
    k: int = FEWSHOT_TOP_K,
) -> list[tuple[str, str, float]]:
    """Busca top-K exemplos few-shot mais similares à query atual.

    Retorna lista de (cliente_msg, agente_resposta, similarity).
    Vazio se não houver exemplos com similaridade mínima.
    """
    if not query.strip() or not agente_slug:
        return []

    try:
        embedding = await _embed(query)
    except Exception as e:
        logger.warning("fewshot_embed_failed", error=str(e))
        return []
    vec_lit = _vector_literal(embedding)

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT cliente_msg, agente_resposta,
                   1 - (embedding <=> %s::vector) AS similarity
              FROM fewshot_example
             WHERE empresa_id = %s
               AND agente_slug = %s
               AND status = 'ready'
               AND embedding IS NOT NULL
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,
            (vec_lit, empresa_id, agente_slug, vec_lit, k),
        )
        rows = await cur.fetchall()

    out: list[tuple[str, str, float]] = []
    for row in rows:
        sim = float(row[2])
        if sim < FEWSHOT_MIN_SIMILARITY:
            break
        out.append((row[0], row[1], sim))
    return out


def format_fewshot_block(examples: list[tuple[str, str, float]]) -> str:
    """Formata exemplos como bloco pra injetar no system prompt."""
    if not examples:
        return ""
    lines = ["", "## Exemplos de respostas que funcionaram bem"]
    for i, (q, a, _sim) in enumerate(examples, 1):
        lines.append(f"\nExemplo {i}:")
        lines.append(f"Cliente: {q[:200]}")
        lines.append(f"Resposta: {a[:300]}")
    lines.append("")
    lines.append("Use esses exemplos como guia de tom e estrutura, mas")
    lines.append("ADAPTE ao contexto atual do cliente. Não copie literal.")
    return "\n".join(lines)


async def capture_examples_from_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int
) -> int:
    """Quando outcome=success, extrai pares (cliente, agente) e persiste.

    Idempotente — se já capturou, não duplica. Retorna qtd inserida.
    """
    async with pool.connection() as conn:
        # Pega outcome via function da mig 067
        cur = await conn.execute(
            "SELECT compute_atendimento_outcome(%s)", (atendimento_id,)
        )
        outcome_row = await cur.fetchone()
        if not outcome_row or outcome_row[0] != "success":
            return 0

        # Já capturou exemplos desse atendimento?
        cur = await conn.execute(
            "SELECT 1 FROM fewshot_example WHERE atendimento_id=%s LIMIT 1",
            (atendimento_id,),
        )
        if await cur.fetchone():
            return 0

        # Pega contexto: agente_atual + empresa_id
        cur = await conn.execute(
            "SELECT empresa_id, agente_atual FROM atendimento WHERE id=%s",
            (atendimento_id,),
        )
        ctx = await cur.fetchone()
        if not ctx or not ctx[1]:
            return 0
        empresa_id, agente_slug = int(ctx[0]), ctx[1]

        # Pega mensagens do atendimento (ordem cronológica)
        cur = await conn.execute(
            """
            SELECT direction, body
              FROM mensagem_log
             WHERE atendimento_id = %s
               AND body IS NOT NULL AND char_length(body) > 5
             ORDER BY created_at ASC
             LIMIT 100
            """,
            (atendimento_id,),
        )
        msgs = await cur.fetchall()

    # Extrai pares (cliente_in, agente_out) consecutivos
    pairs: list[tuple[str, str]] = []
    last_in: str | None = None
    for direction, body in msgs:
        if direction in ("in", "inbound"):
            last_in = body
        elif direction in ("out", "outbound") and last_in:
            pairs.append((last_in[:1000], body[:1500]))
            last_in = None

    if not pairs:
        return 0

    # Pega só o "melhor" par: a última troca antes do encerramento
    # (provavelmente foi a que resolveu).
    selected = pairs[-1:] if pairs else []

    inserted = 0
    for q, a in selected:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO fewshot_example
                  (empresa_id, agente_slug, cliente_msg, agente_resposta,
                   outcome, atendimento_id, status)
                VALUES (%s, %s, %s, %s, 'success', %s, 'pending')
                """,
                (empresa_id, agente_slug, q, a, atendimento_id),
            )
            await conn.commit()
        inserted += 1

    return inserted


async def backfill_embeddings(pool: AsyncConnectionPool, batch: int = 50) -> int:
    """Gera embeddings dos few-shots com status='pending'. Idempotente."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg
              FROM fewshot_example
             WHERE status = 'pending' AND embedding IS NULL
             ORDER BY id
             LIMIT %s
            """,
            (batch,),
        )
        rows = await cur.fetchall()

    updated = 0
    for ex_id, msg in rows:
        try:
            vec = await _embed(msg)
            vec_lit = _vector_literal(vec)
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    UPDATE fewshot_example
                       SET embedding = %s::vector, status = 'ready'
                     WHERE id = %s
                    """,
                    (vec_lit, ex_id),
                )
                await conn.commit()
            updated += 1
        except Exception as e:
            logger.warning("fewshot_embed_fail", id=ex_id, error=str(e))
    return updated
