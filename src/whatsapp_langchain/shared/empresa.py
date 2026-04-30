"""Helpers de multi-tenancy — leitura/validação de empresa por usuário.

Toda query operacional do harness filtra por `empresa_id`. O backend resolve
o id ativo da empresa em duas camadas:

1. Cliente envia header `X-Empresa-Id` (validado contra membership).
2. Sem header, usa a empresa default do usuário (`is_default=TRUE`).

Não há um único user logado no sentido Better Auth — o frontend (Next.js)
envia `X-User-Id` derivado da session, e a API confia nesse header porque a
chamada é protegida por `INTERNAL_SERVICE_TOKEN` (rede interna).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Empresa, EmpresaMembro

logger = structlog.get_logger()


async def list_empresas_of_user(
    pool: AsyncConnectionPool, user_id: str
) -> list[Empresa]:
    """Retorna todas as empresas onde o user é membro, default primeiro."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT e.id, e.nome, e.slug, e.doc, e.plano, e.status,
                   e.config, e.created_at, e.updated_at
              FROM empresa e
              JOIN empresa_membro m ON m.empresa_id = e.id
             WHERE m.user_id = %s
               AND e.status = 'active'
             ORDER BY m.is_default DESC, e.nome ASC
            """,
            (user_id,),
        )
        rows = await cur.fetchall()

    return [
        Empresa(
            id=r[0],
            nome=r[1],
            slug=r[2],
            doc=r[3],
            plano=r[4],
            status=r[5],
            config=r[6] or {},
            created_at=r[7],
            updated_at=r[8],
        )
        for r in rows
    ]


async def get_default_empresa_id(
    pool: AsyncConnectionPool, user_id: str
) -> int | None:
    """Retorna o empresa_id marcado como default pro user (None se não tem)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT empresa_id FROM empresa_membro
             WHERE user_id = %s
             ORDER BY is_default DESC, joined_at ASC
             LIMIT 1
            """,
            (user_id,),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def get_empresa_membership(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> EmpresaMembro | None:
    """Retorna a membership do user numa empresa específica (None se não é membro)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT empresa_id, user_id, role, is_default, joined_at
              FROM empresa_membro
             WHERE empresa_id = %s AND user_id = %s
            """,
            (empresa_id, user_id),
        )
        row = await cur.fetchone()

    if not row:
        return None

    return EmpresaMembro(
        empresa_id=row[0],
        user_id=row[1],
        role=row[2],
        is_default=row[3],
        joined_at=row[4],
    )


async def is_superadmin(pool: AsyncConnectionPool, user_id: str) -> bool:
    """Lookup auth."user".is_superadmin — bypassa validação de membership."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT is_superadmin FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
    return bool(row[0]) if row else False
