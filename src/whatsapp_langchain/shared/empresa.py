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
    """Retorna todas as empresas onde o user é membro, default primeiro.

    Inclui `my_role` (role do user na empresa) pra a UI poder decidir
    o que mostrar (botão "Editar" só pra admin etc).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT e.id, e.nome, e.slug, e.doc, e.plano, e.status,
                   e.config, e.created_at, e.updated_at, m.role
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
            my_role=r[9],
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


# --- M1.x: gestão de empresas e membros ---


_EMPRESA_COLS = (
    "id, nome, slug, doc, plano, status, config, created_at, updated_at"
)


def _row_to_empresa(row) -> Empresa:
    return Empresa(
        id=row[0],
        nome=row[1],
        slug=row[2],
        doc=row[3],
        plano=row[4],
        status=row[5],
        config=row[6] or {},
        created_at=row[7],
        updated_at=row[8],
    )


async def get_empresa_by_id(
    pool: AsyncConnectionPool, empresa_id: int
) -> Empresa | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_EMPRESA_COLS} FROM empresa WHERE id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()
    return _row_to_empresa(row) if row else None


async def create_empresa(
    pool: AsyncConnectionPool,
    nome: str,
    slug: str,
    plano: str,
    doc: str | None,
    criador_user_id: str,
) -> Empresa:
    """Cria empresa e adiciona o criador como admin (is_default=False).

    Usa 1 transação: se a inserção da membership falhar, a empresa
    também é desfeita.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO empresa (nome, slug, plano, doc)
            VALUES (%s, %s, %s, %s)
            RETURNING {_EMPRESA_COLS}
            """,
            (nome, slug, plano, doc),
        )
        row = await cur.fetchone()
        assert row is not None
        empresa = _row_to_empresa(row)

        await conn.execute(
            """
            INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
            VALUES (%s, %s, 'admin', FALSE)
            ON CONFLICT (empresa_id, user_id) DO NOTHING
            """,
            (empresa.id, criador_user_id),
        )
    return empresa


async def update_empresa(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str | None = None,
    slug: str | None = None,
    plano: str | None = None,
    doc: str | None = None,
    status: str | None = None,
) -> Empresa | None:
    """Atualiza campos não-None. Retorna None se a empresa não existe."""
    fields: list[str] = []
    params: list = []
    for name, value in (
        ("nome", nome),
        ("slug", slug),
        ("plano", plano),
        ("doc", doc),
        ("status", status),
    ):
        if value is not None:
            fields.append(f"{name} = %s")
            params.append(value)
    if not fields:
        return await get_empresa_by_id(pool, empresa_id)
    params.append(empresa_id)
    # Os fragments (fields/_EMPRESA_COLS) são whitelist hardcoded acima —
    # nenhum input do user entra na string SQL, só nos %s. f-string é
    # seguro aqui mas pyright marca como str dinâmica; suprimimos com
    # ignore explícito.
    query = (
        f"UPDATE empresa SET {', '.join(fields)}, updated_at = NOW() "
        f"WHERE id = %s RETURNING {_EMPRESA_COLS}"
    )
    async with pool.connection() as conn:
        cur = await conn.execute(query, tuple(params))  # type: ignore[arg-type]
        row = await cur.fetchone()
    return _row_to_empresa(row) if row else None


async def list_members(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[EmpresaMembro]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT empresa_id, user_id, role, is_default, joined_at
              FROM empresa_membro
             WHERE empresa_id = %s
             ORDER BY role ASC, joined_at ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [
        EmpresaMembro(
            empresa_id=r[0],
            user_id=r[1],
            role=r[2],
            is_default=r[3],
            joined_at=r[4],
        )
        for r in rows
    ]


async def add_member(
    pool: AsyncConnectionPool,
    empresa_id: int,
    user_id: str,
    role: str = "operator",
) -> EmpresaMembro:
    """Adiciona membro. Conflito (já é membro) atualiza o role."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
            VALUES (%s, %s, %s, FALSE)
            ON CONFLICT (empresa_id, user_id) DO UPDATE SET role = EXCLUDED.role
            RETURNING empresa_id, user_id, role, is_default, joined_at
            """,
            (empresa_id, user_id, role),
        )
        row = await cur.fetchone()
    assert row is not None
    return EmpresaMembro(
        empresa_id=row[0],
        user_id=row[1],
        role=row[2],
        is_default=row[3],
        joined_at=row[4],
    )


async def update_member_role(
    pool: AsyncConnectionPool,
    empresa_id: int,
    user_id: str,
    role: str,
) -> EmpresaMembro | None:
    """Atualiza role. Quando é último admin sendo demovido, retorna None."""
    if role != "admin":
        # checa se ainda restará outro admin
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT COUNT(*) FROM empresa_membro
                 WHERE empresa_id = %s AND role = 'admin' AND user_id <> %s
                """,
                (empresa_id, user_id),
            )
            row = await cur.fetchone()
            if row and row[0] == 0:
                return None  # último admin — caller raise 409

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE empresa_membro SET role = %s
             WHERE empresa_id = %s AND user_id = %s
            RETURNING empresa_id, user_id, role, is_default, joined_at
            """,
            (role, empresa_id, user_id),
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


async def remove_member(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> bool:
    """Remove membro. Retorna False se for último admin (proteção)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT role FROM empresa_membro WHERE empresa_id = %s AND user_id = %s",
            (empresa_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return False  # não é membro
        if row[0] == "admin":
            cur = await conn.execute(
                """
                SELECT COUNT(*) FROM empresa_membro
                 WHERE empresa_id = %s AND role = 'admin' AND user_id <> %s
                """,
                (empresa_id, user_id),
            )
            count_row = await cur.fetchone()
            if count_row and count_row[0] == 0:
                return False  # último admin
        await conn.execute(
            "DELETE FROM empresa_membro WHERE empresa_id = %s AND user_id = %s",
            (empresa_id, user_id),
        )
    return True


async def is_admin_of(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> bool:
    """True se o user é admin da empresa OU superadmin global."""
    if await is_superadmin(pool, user_id):
        return True
    m = await get_empresa_membership(pool, empresa_id, user_id)
    return m is not None and m.role == "admin"
