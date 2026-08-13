"""Sprint U — helpers de gestão completa de usuários.

Consolida operações que hoje ficam espalhadas entre:
- empresa_membro (membership + role legacy)
- usuario_perfil (RBAC moderno)
- usuario_departamento (associação depto)
- auth.user (Better Auth — name, email, image + custom: telefone, status)

Tudo cross-tenant cuidadoso: usa empresa_scope(bypass=True) onde
operação envolve tabelas globais (auth.user, perfil_acesso global) e
empresa_scope(empresa_id) onde tabela tem RLS por empresa.

Funções principais:
- `list_usuarios_da_empresa` — view enriquecida (avatar + perfis + deptos)
- `criar_usuario_completo` — transação que cobre Better Auth + memberships
- `enriquecer_user` — JOIN único pra evitar N+1
- `set_telefone`, `set_avatar_path` — updates parciais
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


@dataclass
class UsuarioInfo:
    """Snapshot enriquecido de user — pra UI listagem."""

    id: str
    nome: str | None
    email: str | None
    telefone: str | None
    avatar_path: str | None
    image_url: str | None  # Better Auth field (URL externa, ex: Google)
    status: str  # active | disabled
    is_superadmin: bool
    atendente_status: str | None  # online|ausente|pausa|offline|null
    atendente_max_paralelos: int
    last_login_at: datetime | None
    created_at: datetime | None
    # Mig 167 — último convite de acesso enviado no WhatsApp (None = nunca).
    convite_enviado_at: datetime | None

    # Por empresa atual:
    role_legacy: str | None  # empresa_membro.role (admin|operator|viewer)
    is_default_empresa: bool
    perfis: list[dict] = field(default_factory=list)  # [{id, nome, is_system}]
    departamentos: list[dict] = field(default_factory=list)  # [{id, nome}]
    # [{id, nome, provider, is_default}] — conexões atribuídas (mig 111)
    conexoes: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "telefone": self.telefone,
            "avatar_path": self.avatar_path,
            "image_url": self.image_url,
            "status": self.status,
            "is_superadmin": self.is_superadmin,
            "atendente_status": self.atendente_status,
            "atendente_max_paralelos": self.atendente_max_paralelos,
            "last_login_at": (
                self.last_login_at.isoformat() if self.last_login_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "convite_enviado_at": (
                self.convite_enviado_at.isoformat()
                if self.convite_enviado_at
                else None
            ),
            "role_legacy": self.role_legacy,
            "is_default_empresa": self.is_default_empresa,
            "perfis": self.perfis,
            "departamentos": self.departamentos,
            "conexoes": self.conexoes,
        }


# ---------------------------------------------------------------------
# Listagem enriquecida
# ---------------------------------------------------------------------

# Sub-selects reaproveitados por list + get (evita duplicar o JOIN grande).
_PERFIS_SUBQUERY = """
        COALESCE(
            (SELECT json_agg(json_build_object(
                'id', p.id, 'nome', p.nome, 'is_system', p.is_system
             ) ORDER BY p.nome)
             FROM usuario_perfil up
             JOIN perfil_acesso p ON p.id = up.perfil_id
             WHERE up.user_id = u.id AND up.empresa_id = m.empresa_id),
            '[]'::json
        ) AS perfis"""

_DEPTOS_SUBQUERY = """
        COALESCE(
            (SELECT json_agg(json_build_object(
                'id', d.id, 'nome', d.nome
             ) ORDER BY d.nome)
             FROM usuario_departamento ud
             JOIN departamento d ON d.id = ud.departamento_id
             WHERE ud.user_id = u.id AND ud.empresa_id = m.empresa_id),
            '[]'::json
        ) AS departamentos"""

_CONEXOES_SUBQUERY = """
        COALESCE(
            (SELECT json_agg(json_build_object(
                'id', c.id,
                'nome', COALESCE(c.display_name, c.from_number),
                'provider', c.provider,
                'is_default', uc.is_default
             ) ORDER BY uc.is_default DESC, c.id)
             FROM usuario_conexao uc
             JOIN conexao c ON c.id = uc.conexao_id
             WHERE uc.user_id = u.id AND uc.empresa_id = m.empresa_id),
            '[]'::json
        ) AS conexoes"""


def _enriched_sql(*, where_extra: str, tail: str, with_total: bool) -> str:
    """Monta o SELECT enriquecido. `where_extra` entra após `m.empresa_id = %s`.

    Colunas: 0-16 base+perfis+deptos, 17 conexões, 18 total_count (se
    `with_total`). auth.user é global (sem RLS); empresa_membro/usuario_*
    têm RLS — caller usa empresa_scope(bypass=True) + filtro explícito.
    """
    total_col = ", COUNT(*) OVER() AS total_count" if with_total else ""
    return f"""
    SELECT
        u.id, u.name, u.email, u.telefone, u.avatar_path, u.image,
        u.status, u.is_superadmin,
        u.atendente_status, u.atendente_max_paralelos,
        u.last_login_at, u."createdAt", u.convite_enviado_at,
        m.role, m.is_default,
        {_PERFIS_SUBQUERY},
        {_DEPTOS_SUBQUERY},
        {_CONEXOES_SUBQUERY}
        {total_col}
    FROM empresa_membro m
    JOIN auth."user" u ON u.id = m.user_id
    WHERE m.empresa_id = %s {where_extra}
    {tail}
    """


def _row_to_usuario(r: Any) -> UsuarioInfo:
    return UsuarioInfo(
        id=r[0],
        nome=r[1],
        email=r[2],
        telefone=r[3],
        avatar_path=r[4],
        image_url=r[5],
        status=r[6],
        is_superadmin=bool(r[7]),
        atendente_status=r[8],
        atendente_max_paralelos=int(r[9]),
        last_login_at=r[10],
        created_at=r[11],
        convite_enviado_at=r[12],
        role_legacy=r[13],
        is_default_empresa=bool(r[14]),
        perfis=list(r[15]) if r[15] else [],
        departamentos=list(r[16]) if r[16] else [],
        conexoes=list(r[17]) if r[17] else [],
    )


async def list_usuarios_da_empresa(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    search: str | None = None,
    perfil_id: int | None = None,
    departamento_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[UsuarioInfo], int]:
    """Lista membros da empresa enriquecidos + total (pra paginação).

    Retorna `(items, total)` — `total` é o COUNT sem LIMIT/OFFSET, via
    window function (1 round-trip). Filtros opcionais aplicados no SQL.
    """
    params: list[Any] = [empresa_id]
    where_extras: list[str] = []

    if search and search.strip():
        # Case-insensitive em nome/email/telefone
        params.extend([f"%{search.strip()}%"] * 3)
        where_extras.append(
            "(u.name ILIKE %s OR u.email ILIKE %s OR u.telefone ILIKE %s)"
        )
    if status in ("active", "disabled"):
        params.append(status)
        where_extras.append("u.status = %s")
    if perfil_id is not None:
        params.append(perfil_id)
        where_extras.append(
            "EXISTS (SELECT 1 FROM usuario_perfil up "
            "WHERE up.user_id = u.id AND up.empresa_id = m.empresa_id "
            "AND up.perfil_id = %s)"
        )
    if departamento_id is not None:
        params.append(departamento_id)
        where_extras.append(
            "EXISTS (SELECT 1 FROM usuario_departamento ud "
            "WHERE ud.user_id = u.id AND ud.empresa_id = m.empresa_id "
            "AND ud.departamento_id = %s)"
        )

    extras_sql = (" AND " + " AND ".join(where_extras)) if where_extras else ""
    params.append(min(max(limit, 1), 500))
    params.append(max(offset, 0))

    sql = _enriched_sql(
        where_extra=extras_sql,
        tail=(
            "ORDER BY u.last_login_at DESC NULLS LAST, u.name ASC, u.id\n"
            "    LIMIT %s OFFSET %s"
        ),
        with_total=True,
    )

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(sql, tuple(params))  # type: ignore[arg-type]
            rows = await cur.fetchall()

    total = int(rows[0][18]) if rows else 0
    return [_row_to_usuario(r) for r in rows], total


async def get_usuario(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> UsuarioInfo | None:
    """Lookup direto de um user na empresa. Retorna None se não membro."""
    sql = _enriched_sql(where_extra="AND u.id = %s", tail="LIMIT 1", with_total=False)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(sql, (empresa_id, user_id))  # type: ignore[arg-type]
            row = await cur.fetchone()
    return _row_to_usuario(row) if row else None


# ---------------------------------------------------------------------
# Criação / edição de usuário
# ---------------------------------------------------------------------


class TenantValidationError(ValueError):
    """perfis_ids/departamentos_ids que não pertencem à empresa → 422 no route."""


async def _validar_ids_da_empresa(
    conn: Any,
    empresa_id: int,
    perfis_ids: list[int] | None,
    departamentos_ids: list[int] | None,
    conexoes_ids: list[int] | None = None,
) -> None:
    """Garante que perfis/deptos/conexões pertencem à empresa antes de associar.

    Defesa em profundidade além da RLS — erro claro em vez de FK silenciosa
    ou vazamento cross-tenant. Roda dentro da transação do caller.
    """
    checks: list[tuple[str, str, list[int] | None]] = [
        ("perfil_acesso", "Perfis", perfis_ids),
        ("departamento", "Departamentos", departamentos_ids),
        ("conexao", "Conexões", conexoes_ids),
    ]
    for table, rotulo, ids in checks:
        if not ids:
            continue
        # `table` vem de lista hardcoded acima (não é input) — sem injeção.
        sql = f"SELECT id FROM {table} WHERE empresa_id = %s AND id = ANY(%s)"
        cur = await conn.execute(sql, (empresa_id, list(ids)))
        found = {row[0] for row in await cur.fetchall()}
        invalid = sorted(set(ids) - found)
        if invalid:
            raise TenantValidationError(
                f"{rotulo} não pertencem a esta empresa: {invalid}"
            )


async def _sync_conexoes(
    conn: Any,
    user_id: str,
    empresa_id: int,
    conexoes: list[dict] | None,
) -> None:
    """Sync (replace) das conexões atribuídas ao usuário (mig 111).

    `conexoes`: lista de `{"id": int, "is_default": bool}`. Garante no
    máx. 1 default (o primeiro marcado vence). Roda na transação do caller.
    """
    if conexoes is None:
        return
    await conn.execute(
        "DELETE FROM usuario_conexao WHERE user_id = %s AND empresa_id = %s",
        (user_id, empresa_id),
    )
    default_usado = False
    for c in conexoes:
        cid = int(c["id"])
        is_def = bool(c.get("is_default")) and not default_usado
        if is_def:
            default_usado = True
        await conn.execute(
            """
            INSERT INTO usuario_conexao
                (user_id, conexao_id, empresa_id, is_default)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, conexao_id, empresa_id)
            DO UPDATE SET is_default = EXCLUDED.is_default
            """,
            (user_id, cid, empresa_id, is_def),
        )


async def criar_usuario_completo(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    nome: str,
    email: str | None = None,
    telefone: str | None = None,
    role_legacy: str = "operator",
    perfis_ids: list[int] | None = None,
    departamentos_ids: list[int] | None = None,
    conexoes: list[dict] | None = None,
    atendente_max_paralelos: int | None = None,
    criado_por_user_id: str,
) -> UsuarioInfo:
    """Cria user + member + perfis + deptos + conexões em uma transação.

    NÃO cria `auth.account` (credentials) aqui — Better Auth tem seu
    próprio formato de hash de senha (scrypt). A Server Action do
    frontend chama `auth.api.setUserPassword(userId, password)` separado,
    que cria a entry em auth.account corretamente. Esse 2-step é seguro
    porque criar_usuario_completo só roda dentro de transação RBAC-gated.

    Email é opcional: quando NULL, geramos sintético `user-{uuid}@no-email.local`
    pra satisfazer UNIQUE constraint do Better Auth (não usado pra login).

    Retorna `UsuarioInfo` enriquecido — frontend reseta senha em seguida.
    """
    user_id = str(uuid.uuid4())

    # Email sintético se não fornecido (preserva UNIQUE no Better Auth)
    email_final = (
        email.strip().lower()
        if email and email.strip()
        else f"user-{user_id}@no-email.local"
    )

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            async with conn.transaction():
                conexoes_ids = [int(c["id"]) for c in conexoes] if conexoes else None
                await _validar_ids_da_empresa(
                    conn, empresa_id, perfis_ids, departamentos_ids, conexoes_ids
                )
                now = datetime.utcnow()
                await conn.execute(
                    """
                    INSERT INTO auth."user"
                        (id, name, email, telefone, "emailVerified",
                         status, is_superadmin, "createdAt", "updatedAt",
                         atendente_max_paralelos)
                    VALUES (%s, %s, %s, %s, false, 'active', false, %s, %s,
                            COALESCE(%s, 5))
                    """,
                    (
                        user_id,
                        nome,
                        email_final,
                        telefone,
                        now,
                        now,
                        atendente_max_paralelos,
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO empresa_membro
                        (empresa_id, user_id, role, is_default)
                    VALUES (%s, %s, %s, false)
                    """,
                    (empresa_id, user_id, role_legacy),
                )
                for pid in perfis_ids or []:
                    await conn.execute(
                        """
                        INSERT INTO usuario_perfil
                            (user_id, perfil_id, empresa_id, assigned_by_user_id)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (user_id, pid, empresa_id, criado_por_user_id),
                    )
                for did in departamentos_ids or []:
                    await conn.execute(
                        """
                        INSERT INTO usuario_departamento
                            (user_id, departamento_id, empresa_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (user_id, did, empresa_id),
                    )
                await _sync_conexoes(conn, user_id, empresa_id, conexoes)

    logger.info(
        "usuario_criado",
        empresa_id=empresa_id,
        user_id=user_id,
        nome=nome,
        criado_por=criado_por_user_id,
    )

    fetched = await get_usuario(pool, empresa_id, user_id)
    if fetched is None:
        raise RuntimeError(f"Falha ao buscar user recém-criado {user_id}")
    return fetched


async def atualizar_usuario(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    nome: str | None = None,
    email: str | None = None,
    telefone: str | None = None,
    avatar_path: str | None = None,
    role_legacy: str | None = None,
    perfis_ids: list[int] | None = None,
    departamentos_ids: list[int] | None = None,
    conexoes: list[dict] | None = None,
) -> UsuarioInfo | None:
    """Atualiza qualquer combinação de campos. Campos None = não muda."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            async with conn.transaction():
                conexoes_ids = [int(c["id"]) for c in conexoes] if conexoes else None
                await _validar_ids_da_empresa(
                    conn, empresa_id, perfis_ids, departamentos_ids, conexoes_ids
                )
                # auth.user fields
                fields, params = [], []
                for name, value in (
                    ("name", nome),
                    ("email", email.strip().lower() if email else None),
                    ("telefone", telefone),
                    ("avatar_path", avatar_path),
                ):
                    if value is not None:
                        fields.append(f'"{name}" = %s')
                        params.append(value)
                if fields:
                    fields.append('"updatedAt" = NOW()')
                    params.append(user_id)
                    await conn.execute(
                        f'UPDATE auth."user" SET {", ".join(fields)} WHERE id = %s',
                        tuple(params),
                    )

                # empresa_membro.role
                if role_legacy is not None:
                    await conn.execute(
                        "UPDATE empresa_membro SET role = %s "
                        "WHERE empresa_id = %s AND user_id = %s",
                        (role_legacy, empresa_id, user_id),
                    )

                # perfis: sync (replace)
                if perfis_ids is not None:
                    await conn.execute(
                        "DELETE FROM usuario_perfil "
                        "WHERE user_id = %s AND empresa_id = %s",
                        (user_id, empresa_id),
                    )
                    for pid in perfis_ids:
                        await conn.execute(
                            "INSERT INTO usuario_perfil "
                            "(user_id, perfil_id, empresa_id) "
                            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (user_id, pid, empresa_id),
                        )

                # deptos: sync (replace)
                if departamentos_ids is not None:
                    await conn.execute(
                        "DELETE FROM usuario_departamento "
                        "WHERE user_id = %s AND empresa_id = %s",
                        (user_id, empresa_id),
                    )
                    for did in departamentos_ids:
                        await conn.execute(
                            "INSERT INTO usuario_departamento "
                            "(user_id, departamento_id, empresa_id) "
                            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (user_id, did, empresa_id),
                        )

                # conexões: sync (replace) — só se enviado
                await _sync_conexoes(conn, user_id, empresa_id, conexoes)
    return await get_usuario(pool, empresa_id, user_id)


async def verificar_user_existe(pool: AsyncConnectionPool, user_id: str) -> dict | None:
    """Lookup leve em auth.user por id. Pra Server Action de reset senha
    confirmar que user existe antes de chamar Better Auth setUserPassword.

    Sprint U.4 — FIX BUG: busca por user_id direto, não por email.
    Reset funciona mesmo se user.email = NULL (atendente sem email).
    """
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                'SELECT id, name, email FROM auth."user" WHERE id = %s',
                (user_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "email": row[2]}


async def invalidar_sessions(pool: AsyncConnectionPool, user_id: str) -> int:
    """Apaga todas auth.session do user — força re-login. Usado após reset."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                'DELETE FROM auth.session WHERE "userId" = %s', (user_id,)
            )
            await conn.commit()
    return cur.rowcount or 0


async def resolve_user_names(
    pool: AsyncConnectionPool, user_ids: list[str]
) -> dict[str, str]:
    """Mapa `{user_id: nome}` (fallback email) pra um lote de ids. auth.user
    é global (sem RLS). Usado pra enriquecer logs/auditoria com nomes."""
    ids = [u for u in {uid for uid in user_ids if uid}]
    if not ids:
        return {}
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                'SELECT id, COALESCE(name, email) FROM auth."user" WHERE id = ANY(%s)',
                (ids,),
            )
            rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}


async def set_avatar_path(
    pool: AsyncConnectionPool, user_id: str, avatar_path: str | None
) -> None:
    """Atualiza só avatar_path. NULL pra limpar."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                'UPDATE auth."user" SET avatar_path = %s, "updatedAt" = NOW() '
                "WHERE id = %s",
                (avatar_path, user_id),
            )
            await conn.commit()


# ---------------------------------------------------------------------
# Remoção / clonagem
# ---------------------------------------------------------------------


async def contar_admins_empresa(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta membros com role legacy 'admin' (guard de último admin)."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM empresa_membro "
                "WHERE empresa_id = %s AND role = 'admin'",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def get_role_legacy(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> str | None:
    """Role do membro nesta empresa, ou None se não for membro."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT role FROM empresa_membro "
                "WHERE empresa_id = %s AND user_id = %s",
                (empresa_id, user_id),
            )
            row = await cur.fetchone()
    return row[0] if row else None


async def remover_usuario_da_empresa(
    pool: AsyncConnectionPool, empresa_id: int, user_id: str
) -> dict | None:
    """Remove o vínculo do usuário com a empresa (membership + perfis +
    deptos + conexões). Se era a última empresa do user, desabilita o
    `auth.user` e mata as sessions (não faz hard-delete pra preservar FKs
    de auditoria/atendimentos). NÃO apaga arquivo de avatar — caller faz.

    Retorna `{"avatar_path", "auth_disabled"}` ou None se não era membro.
    """
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "SELECT 1 FROM empresa_membro "
                    "WHERE empresa_id = %s AND user_id = %s",
                    (empresa_id, user_id),
                )
                if await cur.fetchone() is None:
                    return None

                cur = await conn.execute(
                    'SELECT avatar_path FROM auth."user" WHERE id = %s',
                    (user_id,),
                )
                row = await cur.fetchone()
                avatar_path = row[0] if row else None

                for table in (
                    "usuario_perfil",
                    "usuario_departamento",
                    "usuario_conexao",
                ):
                    await conn.execute(
                        f"DELETE FROM {table} "  # tabela hardcoded — sem injeção
                        "WHERE user_id = %s AND empresa_id = %s",
                        (user_id, empresa_id),
                    )
                await conn.execute(
                    "DELETE FROM empresa_membro WHERE empresa_id = %s AND user_id = %s",
                    (empresa_id, user_id),
                )

                cur = await conn.execute(
                    "SELECT 1 FROM empresa_membro WHERE user_id = %s LIMIT 1",
                    (user_id,),
                )
                auth_disabled = False
                if await cur.fetchone() is None:
                    await conn.execute(
                        "UPDATE auth.\"user\" SET status = 'disabled', "
                        '"updatedAt" = NOW() WHERE id = %s',
                        (user_id,),
                    )
                    await conn.execute(
                        'DELETE FROM auth.session WHERE "userId" = %s',
                        (user_id,),
                    )
                    auth_disabled = True

    logger.info(
        "usuario_removido",
        empresa_id=empresa_id,
        user_id=user_id,
        auth_disabled=auth_disabled,
    )
    return {"avatar_path": avatar_path, "auth_disabled": auth_disabled}


async def replicar_usuario(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    origem_user_id: str,
    nome: str,
    email: str | None = None,
    telefone: str | None = None,
    criado_por_user_id: str,
) -> UsuarioInfo:
    """Clona perfis + deptos + conexões + role + capacidade de um usuário
    existente pra um novo (paridade ZigChat `replicarUsuario`). Onboarding
    rápido de equipes. Senha gerada pelo fluxo normal do create (frontend)."""
    origem = await get_usuario(pool, empresa_id, origem_user_id)
    if origem is None:
        raise TenantValidationError("Usuário de origem não encontrado nesta empresa.")
    return await criar_usuario_completo(
        pool,
        empresa_id=empresa_id,
        nome=nome,
        email=email,
        telefone=telefone,
        role_legacy=origem.role_legacy or "operator",
        perfis_ids=[int(p["id"]) for p in origem.perfis],
        departamentos_ids=[int(d["id"]) for d in origem.departamentos],
        conexoes=[
            {"id": int(c["id"]), "is_default": bool(c.get("is_default"))}
            for c in origem.conexoes
        ],
        atendente_max_paralelos=origem.atendente_max_paralelos,
        criado_por_user_id=criado_por_user_id,
    )
