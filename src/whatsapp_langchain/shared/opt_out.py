"""Disparador (Task 8) — opt-out / supressão e compliance.

Lista de supressão por empresa: quem pediu STOP/PARAR não recebe disparos.
O worker detecta a palavra-chave e registra aqui; o resolver de disparo
(`shared/disparo.py`) filtra esses telefones antes de enviar.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.campanha import normalize_phone
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

# Palavras (mensagem inteira, case-insensitive) que sinalizam opt-out.
STOP_KEYWORDS: frozenset[str] = frozenset(
    {
        "stop",
        "parar",
        "pare",
        "sair",
        "cancelar",
        "remover",
        "descadastrar",
        "unsubscribe",
    }
)


def is_opt_out_request(body: str | None) -> bool:
    """True se a mensagem inteira é uma palavra-chave de opt-out."""
    return (body or "").strip().lower() in STOP_KEYWORDS


async def registrar_opt_out(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    wa_jid: str,
    telefone: str | None = None,
    motivo: str = "user_request",
    origem: str | None = None,
) -> None:
    """Insere (idempotente) o contato na lista de supressão da empresa."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO disparador_opt_out
                    (empresa_id, wa_jid, telefone, motivo, origem)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (empresa_id, wa_jid) DO NOTHING
                """,
                (empresa_id, wa_jid, telefone, motivo, origem),
            )
            await conn.commit()
    logger.info("opt_out_registrado", empresa_id=empresa_id, motivo=motivo)


async def telefones_suprimidos(
    pool: AsyncConnectionPool, empresa_id: int, telefones: list[str]
) -> set[str]:
    """Dado um conjunto de telefones (E.164), retorna quais estão suprimidos.

    Compara por telefone normalizado. Telefones None/sem match não retornam.
    """
    if not telefones:
        return set()
    norm = {n for n in (normalize_phone(t) for t in telefones) if n}
    if not norm:
        return set()
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT telefone FROM disparador_opt_out
                 WHERE empresa_id = %s AND telefone = ANY(%s)
                """,
                (empresa_id, list(norm)),
            )
            rows = await cur.fetchall()
    return {r[0] for r in rows if r[0]}


async def listar_opt_out(
    pool: AsyncConnectionPool, empresa_id: int, *, limit: int = 500
) -> list[dict]:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, wa_jid, telefone, motivo, origem, created_at
                  FROM disparador_opt_out WHERE empresa_id = %s
                 ORDER BY created_at DESC LIMIT %s
                """,
                (empresa_id, limit),
            )
            rows = await cur.fetchall()
    keys = ["id", "wa_jid", "telefone", "motivo", "origem", "created_at"]
    return [dict(zip(keys, r, strict=True)) for r in rows]


async def remover_opt_out(
    pool: AsyncConnectionPool, empresa_id: int, opt_out_id: int
) -> bool:
    """Remove uma entrada da supressão (re-permite contato). Retorna se removeu."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM disparador_opt_out WHERE id = %s AND empresa_id = %s",
                (opt_out_id, empresa_id),
            )
            await conn.commit()
            return cur.rowcount > 0
