"""CRUD de perfis de acesso + atribuição a usuário (E2.A RBAC).

Coexiste com `empresa_membro.role` legacy. Quando um user tem QUALQUER
perfil atribuído via `usuario_perfil`, as permissões dos perfis tomam
precedência. Sem perfil, fallback usa o role text:

- 'admin'    → equivalente ao perfil "Admin"
- 'operator' → equivalente ao perfil "Operador"
- 'viewer'   → equivalente ao perfil "Leitura"

Migração one-shot via endpoint admin converte explicitamente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# Mapping role legacy → nome de perfil system pra fallback
LEGACY_ROLE_TO_PERFIL: Final[dict[str, str]] = {
    "admin": "Admin",
    "operator": "Operador",
    "viewer": "Leitura",
}


async def list_perfis(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[dict]:
    """Lista perfis da empresa com count de permissões + count de users."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT pa.id, pa.nome, pa.descricao, pa.is_system,
                   pa.created_at, pa.updated_at,
                   (SELECT COUNT(*) FROM perfil_permissao pp WHERE pp.perfil_id = pa.id) AS perms_count,
                   (SELECT COUNT(*) FROM usuario_perfil up WHERE up.perfil_id = pa.id AND up.empresa_id = pa.empresa_id) AS users_count
              FROM perfil_acesso pa
             WHERE pa.empresa_id = %s
             ORDER BY pa.is_system DESC, pa.nome ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "nome": r[1],
            "descricao": r[2],
            "is_system": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "updated_at": r[5].isoformat() if r[5] else None,
            "perms_count": r[6],
            "users_count": r[7],
        }
        for r in rows
    ]


async def get_perfil(
    pool: AsyncConnectionPool, perfil_id: int, empresa_id: int
) -> dict | None:
    """Busca perfil + lista de codigos de permissão."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, nome, descricao, is_system, created_at, updated_at
              FROM perfil_acesso
             WHERE id = %s AND empresa_id = %s
            """,
            (perfil_id, empresa_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        cur = await conn.execute(
            "SELECT permissao_codigo FROM perfil_permissao WHERE perfil_id = %s",
            (perfil_id,),
        )
        perms = [r[0] for r in await cur.fetchall()]
    return {
        "id": row[0],
        "nome": row[1],
        "descricao": row[2],
        "is_system": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
        "updated_at": row[5].isoformat() if row[5] else None,
        "permissoes": perms,
    }


async def create_perfil(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    nome: str,
    descricao: str | None,
    permissoes: list[str],
) -> int:
    """Cria perfil custom com permissões iniciais. Retorna id."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
            VALUES (%s, %s, %s, FALSE)
            RETURNING id
            """,
            (empresa_id, nome, descricao),
        )
        row = await cur.fetchone()
        perfil_id = row[0]
        for codigo in permissoes:
            await conn.execute(
                "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (perfil_id, codigo),
            )
        await conn.commit()
    logger.info("perfil_created", empresa_id=empresa_id, perfil_id=perfil_id, nome=nome)
    return perfil_id


async def update_perfil_permissoes(
    pool: AsyncConnectionPool,
    perfil_id: int,
    empresa_id: int,
    *,
    permissoes: list[str],
    descricao: str | None = None,
) -> bool:
    """Substitui set de permissões + atualiza descrição. Bloqueia is_system."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT is_system FROM perfil_acesso WHERE id = %s AND empresa_id = %s",
            (perfil_id, empresa_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        if row[0]:  # is_system
            raise ValueError("Perfil system não pode ser editado.")

        await conn.execute(
            "DELETE FROM perfil_permissao WHERE perfil_id = %s",
            (perfil_id,),
        )
        for codigo in permissoes:
            await conn.execute(
                "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) VALUES (%s, %s)",
                (perfil_id, codigo),
            )
        if descricao is not None:
            await conn.execute(
                "UPDATE perfil_acesso SET descricao = %s, updated_at = NOW() WHERE id = %s",
                (descricao, perfil_id),
            )
        else:
            await conn.execute(
                "UPDATE perfil_acesso SET updated_at = NOW() WHERE id = %s",
                (perfil_id,),
            )
        await conn.commit()
    logger.info("perfil_updated", empresa_id=empresa_id, perfil_id=perfil_id)
    return True


async def delete_perfil(
    pool: AsyncConnectionPool, perfil_id: int, empresa_id: int
) -> bool:
    """Deleta perfil custom. Bloqueia is_system. Cascade limpa
    perfil_permissao e usuario_perfil."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT is_system FROM perfil_acesso WHERE id = %s AND empresa_id = %s",
            (perfil_id, empresa_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        if row[0]:
            raise ValueError("Perfil system não pode ser deletado.")
        await conn.execute(
            "DELETE FROM perfil_acesso WHERE id = %s AND empresa_id = %s",
            (perfil_id, empresa_id),
        )
        await conn.commit()
    return True


async def assign_perfil(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    perfil_id: int,
    assigned_by_user_id: str | None = None,
) -> None:
    """Atribui perfil a user na empresa. Idempotente."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, assigned_by_user_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, perfil_id, empresa_id) DO NOTHING
            """,
            (user_id, perfil_id, empresa_id, assigned_by_user_id),
        )
        await conn.commit()


async def unassign_perfil(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    perfil_id: int,
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM usuario_perfil WHERE user_id = %s AND perfil_id = %s AND empresa_id = %s",
            (user_id, perfil_id, empresa_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def list_user_perfis(
    pool: AsyncConnectionPool, user_id: str, empresa_id: int
) -> list[dict]:
    """Lista perfis atribuídos ao user na empresa."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT pa.id, pa.nome
              FROM usuario_perfil up
              JOIN perfil_acesso pa ON pa.id = up.perfil_id
             WHERE up.user_id = %s AND up.empresa_id = %s
             ORDER BY pa.nome
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [{"id": r[0], "nome": r[1]} for r in rows]


async def get_user_permissions(
    pool: AsyncConnectionPool, user_id: str, empresa_id: int
) -> set[str]:
    """Resolve set efetivo de permissões do user na empresa.

    Estratégia (em ordem):
    1. Se user é `is_superadmin=true` em auth.user → retorna TODAS as
       permissões do catálogo (acesso global).
    2. Se tem perfis em `usuario_perfil` → união das permissões de todos.
    3. Fallback legacy: lê `empresa_membro.role` e mapeia pro perfil
       system equivalente — pra empresas que ainda não rodaram migração.

    Set vazio = user sem nenhuma permissão (UI esconde tudo, endpoints
    rejeitam tudo).
    """
    async with pool.connection() as conn:
        # 1. Superadmin → tudo
        cur = await conn.execute(
            'SELECT is_superadmin FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
        if row and row[0]:
            cur = await conn.execute("SELECT codigo FROM permissao")
            return {r[0] for r in await cur.fetchall()}

        # 2. Perfis explícitos
        cur = await conn.execute(
            """
            SELECT DISTINCT pp.permissao_codigo
              FROM usuario_perfil up
              JOIN perfil_permissao pp ON pp.perfil_id = up.perfil_id
             WHERE up.user_id = %s AND up.empresa_id = %s
            """,
            (user_id, empresa_id),
        )
        explicitos = {r[0] for r in await cur.fetchall()}
        if explicitos:
            return explicitos

        # 3. Fallback legacy via empresa_membro.role
        cur = await conn.execute(
            "SELECT role FROM empresa_membro WHERE user_id = %s AND empresa_id = %s",
            (user_id, empresa_id),
        )
        row = await cur.fetchone()
        if not row:
            return set()
        legacy_role = row[0]
        nome_perfil = LEGACY_ROLE_TO_PERFIL.get(legacy_role)
        if not nome_perfil:
            return set()
        cur = await conn.execute(
            """
            SELECT pp.permissao_codigo
              FROM perfil_acesso pa
              JOIN perfil_permissao pp ON pp.perfil_id = pa.id
             WHERE pa.empresa_id = %s AND pa.nome = %s AND pa.is_system = TRUE
            """,
            (empresa_id, nome_perfil),
        )
        return {r[0] for r in await cur.fetchall()}


async def migrate_empresa_legacy_to_perfis(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict:
    """One-shot: converte empresa_membro.role → usuario_perfil.

    Lê todos os membros da empresa, atribui o perfil system equivalente
    ao role atual. Não remove a coluna `role` (mantida pra fallback +
    rollback).
    """
    from whatsapp_langchain.shared.permissoes import seed_default_perfis

    # Garante que os perfis system existem
    await seed_default_perfis(pool, empresa_id)

    # Mapeia nomes → ids
    perfis = await list_perfis(pool, empresa_id)
    nome_to_id = {p["nome"]: p["id"] for p in perfis}

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT user_id, role FROM empresa_membro WHERE empresa_id = %s",
            (empresa_id,),
        )
        membros = await cur.fetchall()

    converted = 0
    skipped = 0
    for user_id, role in membros:
        nome = LEGACY_ROLE_TO_PERFIL.get(role)
        if not nome or nome not in nome_to_id:
            skipped += 1
            continue
        await assign_perfil(
            pool,
            empresa_id=empresa_id,
            user_id=user_id,
            perfil_id=nome_to_id[nome],
        )
        converted += 1

    logger.info(
        "rbac_legacy_migrated",
        empresa_id=empresa_id,
        converted=converted,
        skipped=skipped,
    )
    return {"converted": converted, "skipped": skipped, "total_membros": len(membros)}
