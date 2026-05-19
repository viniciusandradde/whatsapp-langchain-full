"""Notas internas na timeline do atendimento (Sprint Atendimento UX 1.3).

Notas vivem na MESMA tabela das mensagens (message_queue) com
`interna=true` (mig 087). Trade-off: timeline única ordenada por tempo
sem precisar de UNION/merge no frontend. Worker NUNCA envia outbound
quando interna=true (gate explícito em shared/outbound.py).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def create_nota_interna(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    empresa_id: int,
    user_id: str,
    texto: str,
) -> dict:
    """Insere nota interna na timeline do atendimento.

    Joga em message_queue com status='done' + interna=true. Não vai pra
    fila de worker (status≠queued), não dispara outbound. Aparece em
    GET /mensagens junto com as outras msgs.

    Resolve `phone_number`/`agent_id` do atendimento (necessários por
    constraints NOT NULL da mig 001).
    """
    async with pool.connection() as conn:
        # Resolve metadados do atendimento (cliente.telefone + conexao_id + agente)
        cur = await conn.execute(
            """
            SELECT a.conexao_id, a.agente_atual, c.telefone
              FROM atendimento a
              JOIN cliente c ON c.id = a.cliente_id
             WHERE a.id = %s AND a.empresa_id = %s
            """,
            (atendimento_id, empresa_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError(
                f"Atendimento {atendimento_id} não pertence à empresa {empresa_id}"
            )
        conexao_id, agente_atual, phone = row
        thread_id = f"{phone}:{agente_atual}"

        cur = await conn.execute(
            """
            INSERT INTO message_queue (
                empresa_id, conexao_id, atendimento_id,
                phone_number, agent_id, thread_id,
                incoming_message, response, normalized_input,
                status, process_after, processed_at,
                interna, criado_por_user_id
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                'done', NOW(), NOW(),
                TRUE, %s
            )
            RETURNING id, created_at
            """,
            (
                empresa_id,
                conexao_id,
                atendimento_id,
                phone,
                agente_atual,
                thread_id,
                "",  # incoming_message vazio (nota é só "response")
                texto,
                f"nota_interna:{user_id}",
                user_id,
            ),
        )
        inserted = await cur.fetchone()
        # Bump last_message_at pra ordenar atendimento na lista
        await conn.execute(
            """
            UPDATE atendimento
               SET last_message_at = NOW(), updated_at = NOW()
             WHERE id = %s
            """,
            (atendimento_id,),
        )
        await conn.commit()
    assert inserted is not None
    logger.info(
        "nota_interna_criada",
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        user_id=user_id,
        msg_id=inserted[0],
    )
    return {
        "id": inserted[0],
        "interna": True,
        "criado_por_user_id": user_id,
        "response": texto,
        "created_at": inserted[1].isoformat() if inserted[1] else None,
    }
