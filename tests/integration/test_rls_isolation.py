"""Sprint A — testes de isolamento RLS Postgres.

Valida que policies em mig 096 funcionam como fail-safe:
- Sem context: vê todas as rows (modo permissive compat)
- Com context empresa=A: vê só rows da empresa A
- Com bypass_rls=True: vê tudo (superadmin)

Requer Docker stack rodando (psycopg real, não mock).
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
import pytest_asyncio
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.db import with_empresa_context

pytestmark = [pytest.mark.docker_demo, pytest.mark.asyncio(loop_scope="module")]

_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def database_url() -> str:
    """URL como SUPERUSER (postgres) — usada pelo setup/teardown."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5434/whatsapp_langchain",
    )


@pytest.fixture(scope="module")
def database_url_app() -> str:
    """URL como chat_nexus_app (NOBYPASSRLS) — usada pra validar RLS real.

    Esperado em env: DATABASE_URL_APP_TEST setada. Sem ela, fallback pro
    DATABASE_URL normal (skip silencioso dos tests que dependem de RLS
    real — vão dar xfail).
    """
    return os.environ.get(
        "DATABASE_URL_APP_TEST",
        os.environ.get("DATABASE_URL_APP", ""),
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool(database_url: str):
    """Pool como superuser — pra setup/teardown e tests de bypass."""
    p = AsyncConnectionPool(conninfo=database_url, min_size=1, max_size=3, open=False)
    await p.open()
    yield p
    await p.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool_app(database_url_app: str):
    """Pool como chat_nexus_app (NOBYPASSRLS) — pra validar RLS de verdade.

    Skip se DATABASE_URL_APP_TEST não setada (CI sem role configurado).
    """
    if not database_url_app:
        pytest.skip(
            "DATABASE_URL_APP_TEST não setada — pula tests que validam "
            "RLS real (precisa role chat_nexus_app NOBYPASSRLS)."
        )
    p = AsyncConnectionPool(
        conninfo=database_url_app, min_size=1, max_size=3, open=False
    )
    await p.open()
    yield p
    await p.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def empresas(pool: AsyncConnectionPool) -> dict[str, int]:
    """Cria 2 empresas isoladas + 1 hook em cada (tabela com RLS ativo)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO empresa (nome, slug, status, config)
            VALUES (%s, %s, 'active', '{}')
            RETURNING id
            """,
            (f"RLS Test A {_RUN}", f"rls-test-a-{_RUN}"),
        )
        row = await cur.fetchone()
        assert row is not None
        empresa_a = int(row[0])

        cur = await conn.execute(
            """
            INSERT INTO empresa (nome, slug, status, config)
            VALUES (%s, %s, 'active', '{}')
            RETURNING id
            """,
            (f"RLS Test B {_RUN}", f"rls-test-b-{_RUN}"),
        )
        row = await cur.fetchone()
        assert row is not None
        empresa_b = int(row[0])

        # Hook na A
        await conn.execute(
            """
            INSERT INTO hook (empresa_id, nome, evento, url, ativo)
            VALUES (%s, %s, %s, %s, true)
            """,
            (empresa_a, f"hook-a-{_RUN}", "mensagem.recebida", "https://a.example/h"),
        )
        # Hook na B
        await conn.execute(
            """
            INSERT INTO hook (empresa_id, nome, evento, url, ativo)
            VALUES (%s, %s, %s, %s, true)
            """,
            (empresa_b, f"hook-b-{_RUN}", "mensagem.recebida", "https://b.example/h"),
        )
        await conn.commit()

    yield {"a": empresa_a, "b": empresa_b}

    # Teardown: CASCADE remove hooks também
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM empresa WHERE id IN (%s, %s)", (empresa_a, empresa_b)
        )
        await conn.commit()


class TestRlsIsolation:
    async def test_sem_context_app_role_ve_zero_strict(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Sprint A.2.3 STRICT: app role sem context = 0 rows (deny default)."""
        async with pool_app.connection() as conn:
            # Limpa context que o wrapper pode ter setado de runs anteriores
            await conn.execute("SELECT set_config('app.empresa_id', '', false)")
            await conn.execute("SELECT set_config('app.bypass_rls', '', false)")
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        assert len(rows) == 0, (
            f"STRICT broken: sem context, app role viu {len(rows)} rows. "
            "Esperado 0 (deny default)."
        )

    async def test_sem_context_superuser_ve_tudo(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Sanidade: superuser (postgres) sempre vê tudo (BYPASSRLS implícito)."""
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["a"] in ids
        assert empresas["b"] in ids

    async def test_context_empresa_a_filtra_so_a(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Com app.empresa_id = A: SELECT hook só retorna hooks da A.

        Usa pool_app (chat_nexus_app) pra RLS valer de fato (superuser
        bypassaria). Após Sprint A.2.6, esse test passa em produção.
        """
        async with with_empresa_context(pool_app, empresas["a"]) as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["a"] in ids
        assert empresas["b"] not in ids, (
            f"VAZAMENTO RLS: empresa A viu hook da B {ids}"
        )

    async def test_context_empresa_b_filtra_so_b(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Inverso: context=B só vê B."""
        async with with_empresa_context(pool_app, empresas["b"]) as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["b"] in ids
        assert empresas["a"] not in ids, (
            f"VAZAMENTO RLS: empresa B viu hook da A {ids}"
        )

    async def test_bypass_rls_ve_tudo(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Superadmin com bypass_rls=True vê hooks de todas as empresas."""
        async with with_empresa_context(pool_app, None, bypass_rls=True) as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["a"] in ids
        assert empresas["b"] in ids

    async def test_insert_empresa_errada_bloqueado(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Context=A tentando INSERT pra empresa_id=B → WITH CHECK rejeita.

        Postgres lança `InsufficientPrivilege` (não CheckViolation) quando
        policy WITH CHECK retorna FALSE — mensagem 'new row violates
        row-level security policy for table'.
        """
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with with_empresa_context(pool_app, empresas["a"]) as conn:
                await conn.execute(
                    """
                    INSERT INTO hook (empresa_id, nome, evento, url, ativo)
                    VALUES (%s, %s, %s, %s, true)
                    """,
                    (
                        empresas["b"],
                        f"forjado-{_RUN}",
                        "mensagem.recebida",
                        "https://forjado.example",
                    ),
                )

    async def test_update_cross_tenant_zero_rows(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """UPDATE em hook de B com context=A deve afetar 0 rows (RLS filtra)."""
        async with with_empresa_context(pool_app, empresas["a"]) as conn:
            cur = await conn.execute(
                "UPDATE hook SET ativo = false WHERE empresa_id = %s",
                (empresas["b"],),
            )
            assert cur.rowcount == 0, (
                f"VAZAMENTO RLS: empresa A conseguiu UPDATE em hook da B "
                f"({cur.rowcount} rows)"
            )

    async def test_delete_cross_tenant_zero_rows(
        self, pool_app: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """DELETE em hook de B com context=A deve afetar 0 rows (RLS filtra)."""
        async with with_empresa_context(pool_app, empresas["a"]) as conn:
            cur = await conn.execute(
                "DELETE FROM hook WHERE empresa_id = %s",
                (empresas["b"],),
            )
            assert cur.rowcount == 0, (
                f"VAZAMENTO RLS: empresa A conseguiu DELETE em hook da B "
                f"({cur.rowcount} rows)"
            )

    async def test_role_app_eh_nobypassrls(
        self, pool_app: AsyncConnectionPool
    ):
        """Sanidade: role app NÃO tem rolbypassrls (senão tests são farsa)."""
        async with pool_app.connection() as conn:
            cur = await conn.execute(
                "SELECT rolname, rolbypassrls, rolsuper "
                "FROM pg_roles WHERE rolname = current_user"
            )
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "chat_nexus_app", (
            f"Esperado chat_nexus_app, conectou como {row[0]}"
        )
        assert row[1] is False, "chat_nexus_app não pode ter BYPASSRLS"
        assert row[2] is False, "chat_nexus_app não pode ser SUPERUSER"

    async def test_with_empresa_context_requer_arg(
        self, pool: AsyncConnectionPool
    ):
        """Sanidade: chamar sem empresa_id e sem bypass → ValueError."""
        with pytest.raises(ValueError, match="empresa_id ou bypass_rls"):
            async with with_empresa_context(pool, None) as _:
                pass
