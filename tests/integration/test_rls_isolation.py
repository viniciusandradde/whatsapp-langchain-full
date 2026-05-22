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
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5434/whatsapp_langchain",
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool(database_url: str):
    p = AsyncConnectionPool(conninfo=database_url, min_size=1, max_size=3, open=False)
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
    async def test_sem_context_ve_tudo_compat(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Modo permissive: sem app.empresa_id setado, vê hooks das duas empresas."""
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["a"] in ids
        assert empresas["b"] in ids

    @pytest.mark.xfail(
        reason="RLS é bypassado quando app conecta como role SUPERUSER "
        "(postgres). Sprint futura: criar role chat_nexus_app sem BYPASSRLS "
        "+ GRANTs apropriados. Sem isso, helper apenas seta o context mas "
        "Postgres ignora as policies. Mig 096 + helper ficam prontos pra "
        "esse momento."
    )
    async def test_context_empresa_a_filtra_so_a(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Com app.empresa_id = A: SELECT hook só retorna hooks da A.

        Falha esperada hoje (xfail) pelo bypass do superuser. Quando o
        role da app deixar de ser superuser, test passa automaticamente
        (sinal de que RLS está enforcing) e o xfail deve ser removido.
        """
        async with with_empresa_context(pool, empresas["a"]) as conn:
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

    @pytest.mark.xfail(
        reason="RLS bypassado pelo superuser — ver test_context_empresa_a_filtra_so_a"
    )
    async def test_context_empresa_b_filtra_so_b(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Inverso: context=B só vê B. Mesma situação do test_context_a (xfail)."""
        async with with_empresa_context(pool, empresas["b"]) as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["b"] in ids
        assert empresas["a"] not in ids

    async def test_bypass_rls_ve_tudo(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Superadmin com bypass_rls=True vê hooks de todas as empresas."""
        async with with_empresa_context(pool, None, bypass_rls=True) as conn:
            cur = await conn.execute(
                "SELECT empresa_id FROM hook WHERE empresa_id IN (%s, %s)",
                (empresas["a"], empresas["b"]),
            )
            rows = await cur.fetchall()
        ids = {r[0] for r in rows}
        assert empresas["a"] in ids
        assert empresas["b"] in ids

    @pytest.mark.xfail(
        reason="RLS bypassado pelo superuser — ver test_context_empresa_a_filtra_so_a"
    )
    async def test_insert_empresa_errada_bloqueado(
        self, pool: AsyncConnectionPool, empresas: dict[str, int]
    ):
        """Context=A tentando INSERT pra empresa_id=B → WITH CHECK rejeita.

        xfail hoje (superuser bypass). Após criação do role app, esse
        INSERT deve falhar com CheckViolation porque o WITH CHECK da
        policy avalia `_rls_tenant_match(B) = false` quando context=A.
        """
        with pytest.raises(psycopg.errors.CheckViolation):
            async with with_empresa_context(pool, empresas["a"]) as conn:
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

    async def test_with_empresa_context_requer_arg(
        self, pool: AsyncConnectionPool
    ):
        """Sanidade: chamar sem empresa_id e sem bypass → ValueError."""
        with pytest.raises(ValueError, match="empresa_id ou bypass_rls"):
            async with with_empresa_context(pool, None) as _:
                pass
