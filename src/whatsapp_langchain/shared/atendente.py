"""Helpers de gestão do atendente humano (Sprint G).

`atendente_status` em `auth.user` (mig 062): online|ausente|pausa|offline.
`atendente_status_at`: heartbeat client-side (último ping de prova-de-vida).
`atendente_max_paralelos`: capacidade default 5 atendimentos paralelos.

Decisões:
- Status é manual (atendente clica) + auto-offline quando heartbeat > 5min.
- `pick_best_atendente` (Sprint I) usa só users com `status='online'` e
  ratio (count_abertos / max_paralelos) menor.
- Endpoint claim (Sprint G.3) valida count_paralelos < max antes de atribuir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


_STATUS_VALIDOS = frozenset({"online", "ausente", "pausa", "offline"})


@dataclass
class AtendenteStatus:
    """Estado runtime de um atendente — mistura colunas de auth.user
    com agregados (count_abertos)."""

    user_id: str
    nome: str | None
    email: str | None
    image: str | None
    is_active: bool  # auth.user.status='active'
    atendente_status: str | None
    atendente_status_at: Any
    atendente_max_paralelos: int
    count_atendimentos_abertos: int

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "nome": self.nome,
            "email": self.email,
            "image": self.image,
            "is_active": self.is_active,
            "atendente_status": self.atendente_status,
            "atendente_status_at": (
                self.atendente_status_at.isoformat()
                if self.atendente_status_at
                else None
            ),
            "atendente_max_paralelos": self.atendente_max_paralelos,
            "count_atendimentos_abertos": self.count_atendimentos_abertos,
            "ratio_capacidade": (
                self.count_atendimentos_abertos / self.atendente_max_paralelos
                if self.atendente_max_paralelos > 0
                else 1.0
            ),
        }


# --- Status / Heartbeat ---


async def set_status(
    pool: AsyncConnectionPool,
    user_id: str,
    *,
    status: str,
) -> None:
    """Atualiza status do atendente. Levanta ValueError em status inválido."""
    if status not in _STATUS_VALIDOS:
        raise ValueError(f"status inválido: {status!r} (use {_STATUS_VALIDOS})")
    async with pool.connection() as conn:
        await conn.execute(
            'UPDATE auth."user" SET atendente_status = %s, '
            'atendente_status_at = NOW(), "updatedAt" = NOW() WHERE id = %s',
            (status, user_id),
        )
        await conn.commit()
    logger.info("atendente_status_set", user_id=user_id, status=status)


async def heartbeat(pool: AsyncConnectionPool, user_id: str) -> None:
    """Atualiza apenas `atendente_status_at` (prova-de-vida).

    NÃO muda o status — admin/atendente decide manualmente. O worker
    `mark_idle_offline` derruba pra offline quando passa 5min sem heartbeat.
    """
    async with pool.connection() as conn:
        await conn.execute(
            'UPDATE auth."user" SET atendente_status_at = NOW() WHERE id = %s',
            (user_id,),
        )
        await conn.commit()


async def mark_idle_offline(
    pool: AsyncConnectionPool, *, idle_seconds: int = 300
) -> int:
    """Worker job — marca offline qualquer user `online` sem heartbeat há N s.

    Retorna quantos users foram afetados. Roda em loop de 60s no worker.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            'UPDATE auth."user" '
            "SET atendente_status = 'offline', "
            '    atendente_status_at = NOW(), "updatedAt" = NOW() '
            "WHERE atendente_status = 'online' "
            "  AND (atendente_status_at IS NULL "
            "       OR atendente_status_at < NOW() - INTERVAL '1 second' * %s)",
            (idle_seconds,),
        )
        await conn.commit()
        n = cur.rowcount or 0
    if n > 0:
        logger.info("atendente_idle_offline", count=n, idle_seconds=idle_seconds)
    return n


# --- Capacidade ---


async def count_atendimentos_user_abertos(
    pool: AsyncConnectionPool, user_id: str, empresa_id: int
) -> int:
    """Conta atendimentos atribuídos ao user com status aguardando|em_andamento."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM atendimento "
            "WHERE empresa_id = %s AND assigned_to_user_id = %s "
            "  AND status IN ('aguardando', 'em_andamento')",
            (empresa_id, user_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def get_max_paralelos(pool: AsyncConnectionPool, user_id: str) -> int:
    """Lê limite de atendimentos paralelos do user (default 5)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT atendente_max_paralelos FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 5


async def set_max_paralelos(
    pool: AsyncConnectionPool, user_id: str, max_paralelos: int
) -> None:
    """Atualiza limite. Levanta ValueError fora de [1, 50]."""
    if not 1 <= max_paralelos <= 50:
        raise ValueError("max_paralelos deve estar entre 1 e 50")
    async with pool.connection() as conn:
        await conn.execute(
            'UPDATE auth."user" SET atendente_max_paralelos = %s, '
            '"updatedAt" = NOW() WHERE id = %s',
            (max_paralelos, user_id),
        )
        await conn.commit()


# --- Listagem da empresa ---


async def list_atendentes_empresa(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[AtendenteStatus]:
    """Lista todos os membros da empresa com status + count atendimentos.

    Inclui users com status NULL (não-atendentes ainda); admin pode setar
    `atendente_max_paralelos` diretamente. Conta `assigned_to_user_id` em
    aberto pra cada user via subselect.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT u.id, u.name, u.email, u.image,
                   COALESCE(u.status, 'active') AS user_status,
                   u.atendente_status, u.atendente_status_at,
                   u.atendente_max_paralelos,
                   (SELECT COUNT(*) FROM atendimento a
                     WHERE a.empresa_id = %s
                       AND a.assigned_to_user_id = u.id
                       AND a.status IN ('aguardando', 'em_andamento')) AS abertos
              FROM auth."user" u
              JOIN empresa_membro em ON em.user_id = u.id
             WHERE em.empresa_id = %s
             ORDER BY
               CASE u.atendente_status
                 WHEN 'online' THEN 0
                 WHEN 'ausente' THEN 1
                 WHEN 'pausa' THEN 2
                 WHEN 'offline' THEN 3
                 ELSE 4
               END,
               u.name NULLS LAST
            """,
            (empresa_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [
        AtendenteStatus(
            user_id=row[0],
            nome=row[1],
            email=row[2],
            image=row[3],
            is_active=(row[4] == "active"),
            atendente_status=row[5],
            atendente_status_at=row[6],
            atendente_max_paralelos=row[7] or 5,
            count_atendimentos_abertos=int(row[8]),
        )
        for row in rows
    ]


# --- Routing capacity-based (Sprint I) ---


async def pick_best_atendente(
    pool: AsyncConnectionPool, *, empresa_id: int, departamento_id: int
) -> str | None:
    """Retorna user_id do melhor atendente pra atribuir.

    Critérios:
    1. Vinculado ao departamento via usuario_departamento
    2. auth.user.status = 'active'
    3. atendente_status = 'online'
    4. count_atendimentos_abertos < atendente_max_paralelos
    5. Menor ratio (count/max) — desempate por menor count absoluto.

    Retorna None se ninguém disponível — atendimento fica na fila aguardando
    claim manual.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH abertos AS (
                SELECT assigned_to_user_id, COUNT(*) AS n
                  FROM atendimento
                 WHERE empresa_id = %s
                   AND assigned_to_user_id IS NOT NULL
                   AND status IN ('aguardando', 'em_andamento')
                 GROUP BY assigned_to_user_id
            )
            SELECT u.id,
                   COALESCE(a.n, 0) AS abertos,
                   u.atendente_max_paralelos
              FROM auth."user" u
              JOIN usuario_departamento ud
                ON ud.user_id = u.id AND ud.empresa_id = %s
              LEFT JOIN abertos a ON a.assigned_to_user_id = u.id
             WHERE ud.departamento_id = %s
               AND COALESCE(u.status, 'active') = 'active'
               AND u.atendente_status = 'online'
               AND COALESCE(a.n, 0) < u.atendente_max_paralelos
             ORDER BY (COALESCE(a.n, 0)::float / GREATEST(u.atendente_max_paralelos, 1))
                      ASC, COALESCE(a.n, 0) ASC, u.id
             LIMIT 1
            """,
            (empresa_id, empresa_id, departamento_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    logger.info(
        "pick_best_atendente",
        empresa_id=empresa_id,
        departamento_id=departamento_id,
        user_id=row[0],
        atendimentos_abertos=row[1],
        max_paralelos=row[2],
    )
    return row[0]
