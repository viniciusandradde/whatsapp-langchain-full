"""Pool de conexões PostgreSQL e utilitários de banco de dados.

Gerencia um pool singleton de conexões assíncronas usando psycopg.
O pool é criado no startup da aplicação (lifespan) e fechado no shutdown.

Uso:
    from whatsapp_langchain.shared.db import get_pool, close_pool, run_migrations

    # No lifespan da aplicação:
    pool = await get_pool()
    await run_migrations(pool)
    # ... app roda ...
    await close_pool()
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.rls_context import get_request_context

logger = structlog.get_logger()

# Singleton do pool de conexões
pool: AsyncConnectionPool | None = None
MIGRATIONS_LOCK_ID = 8_642_000
LANGGRAPH_BOOTSTRAP_LOCK_ID = 8_642_001


def _resolve_migrations_dir() -> Path:
    """Resolve o diretório de migrações para dev local e Docker.

    Em desenvolvimento com código-fonte, `__file__` aponta para:
    `.../src/whatsapp_langchain/shared/db.py` e o caminho relativo funciona.

    Em Docker com pacote instalado no site-packages, as migrações ficam em
    `/app/db/migrations`, então usamos cwd como fallback.
    """
    candidates = [
        # Dev local (código em src/)
        Path(__file__).resolve().parents[3] / "db" / "migrations",
        # Docker/execução a partir do WORKDIR do projeto
        Path.cwd() / "db" / "migrations",
        # Fallback explícito para imagem padrão deste projeto
        Path("/app/db/migrations"),
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    # Mantém comportamento previsível mesmo se diretório estiver ausente
    return candidates[0]


# Diretório de migrações
MIGRATIONS_DIR = _resolve_migrations_dir()


async def _acquire_advisory_lock(conn: AsyncConnection, lock_id: int) -> None:
    """Adquire advisory lock sem deixar transação ociosa bloqueando DDL concorrente."""
    while True:
        cursor = await conn.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
        locked = (await cursor.fetchone())[0]
        await conn.commit()
        if locked:
            return
        await asyncio.sleep(0.1)


async def _release_advisory_lock(conn: AsyncConnection, lock_id: int) -> None:
    """Libera advisory lock e encerra a transação do comando."""
    await conn.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
    await conn.commit()


class _RlsAwarePool:
    """Sprint A.2.4 — wrapper de AsyncConnectionPool que injeta RLS context.

    Quando código pega uma conexão via `async with pool.connection() as conn:`,
    o wrapper:
      1. Lê o contextvar atual (`get_request_context()`)
      2. Se empresa_id setado → executa `SET app.empresa_id = X` (session-level,
         vale pra qualquer query subsequente sem precisar de transação)
      3. Se bypass → executa `SET app.bypass_rls = 'true'`
      4. yields a conn pro código original
      5. Finally: limpa setting (`SET app.empresa_id = ''`) ANTES de devolver
         pro pool — evita vazamento de context entre requests

    Sem context setado (worker sistema, scripts): conexão entregue limpa,
    RLS opera em modo permissive (mig 096 — passa se context vazio).

    Mantém compatibilidade 100% com código existente: signature de
    `pool.connection()` inalterada, atributos não interceptados são
    proxied via __getattr__.
    """

    def __init__(self, inner: AsyncConnectionPool) -> None:
        self._inner = inner

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        async with self._inner.connection() as conn:
            empresa_id, bypass = get_request_context()
            try:
                if bypass:
                    await conn.execute(
                        "SELECT set_config('app.bypass_rls', 'true', false)"
                    )
                elif empresa_id is not None:
                    await conn.execute(
                        "SELECT set_config('app.empresa_id', %s, false)",
                        (str(empresa_id),),
                    )
                yield conn
            finally:
                # Limpa context antes de conn voltar pro pool. Sem isso,
                # próxima request pode pegar essa conn com app.empresa_id
                # da request anterior — vazamento cross-tenant silencioso.
                try:
                    await conn.execute(
                        "SELECT set_config('app.empresa_id', '', false)"
                    )
                    await conn.execute(
                        "SELECT set_config('app.bypass_rls', '', false)"
                    )
                except Exception as exc:
                    logger.warning(
                        "rls_context_cleanup_failed", error=str(exc)
                    )

    def __getattr__(self, name: str) -> Any:
        """Proxy não-interceptado pro pool original (open/close/etc)."""
        return getattr(self._inner, name)


async def get_pool() -> AsyncConnectionPool:
    """Retorna o pool de conexões da APLICAÇÃO (runtime), criando se necessário.

    O pool é singleton — chamadas subsequentes retornam a mesma instância.
    Desde Sprint A.2.4, retorna um `_RlsAwarePool` wrapper que injeta
    automaticamente `SET app.empresa_id` em cada conexão entregue.

    Sprint A.2.6: usa `settings.database_url_app` se setado (role
    `chat_nexus_app` NOBYPASSRLS), senão fallback `settings.database_url`
    (legacy — postgres superuser, RLS efetivamente inerte). Migrations
    e bootstrap (auth) usam `get_migrator_pool()` que SEMPRE usa
    `database_url` (superuser).

    Returns:
        Pool de conexões assíncronas (RlsAwarePool wrapper).
    """
    global pool
    if pool is None:
        url = settings.database_url_app or settings.database_url
        role_label = "chat_nexus_app" if settings.database_url_app else "postgres"
        inner_pool = AsyncConnectionPool(
            conninfo=url,
            min_size=2,
            max_size=10,
            open=False,
        )
        await inner_pool.open()
        pool = _RlsAwarePool(inner_pool)  # type: ignore[assignment]
        db_host = url.split("@")[-1]
        logger.info(
            "db_pool_created",
            database_url=db_host,
            rls_wrapped=True,
            role=role_label,
            rls_enforced=role_label != "postgres",
        )
    return pool  # type: ignore[return-value]


# Migrator pool (singleton separado, usa superuser sempre)
_migrator_pool: AsyncConnectionPool | None = None


async def get_migrator_pool() -> AsyncConnectionPool:
    """Pool específico pra migrations + bootstrap (sempre superuser).

    Sprint A.2.6: migrations precisam DDL + bypass de RLS pra rodar
    `INSERT INTO _migrations` em qualquer momento. Mantém `database_url`
    (postgres) e NÃO usa o wrapper RLS (queries de migration são global).

    Singleton min/max=1 — só usado no startup, evita pool ocioso.
    """
    global _migrator_pool
    if _migrator_pool is None:
        _migrator_pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=2,
            open=False,
        )
        await _migrator_pool.open()
        logger.info(
            "db_migrator_pool_created",
            database_url=settings.database_url.split("@")[-1],
        )
    return _migrator_pool


async def close_pool() -> None:
    """Fecha o(s) pool(s) de conexões.

    Chamado no shutdown da aplicação para liberar recursos.
    Fecha tanto o pool da app quanto o migrator pool (se criado).
    """
    global pool, _migrator_pool
    if pool is not None:
        await pool.close()
        pool = None
        logger.info("db_pool_closed")
    if _migrator_pool is not None:
        await _migrator_pool.close()
        _migrator_pool = None
        logger.info("db_migrator_pool_closed")


@asynccontextmanager
async def with_empresa_context(
    db_pool: AsyncConnectionPool,
    empresa_id: int | None,
    *,
    bypass_rls: bool = False,
) -> AsyncIterator[AsyncConnection]:
    """Sprint A — abre conexão do pool com RLS context setado.

    Uso:
        async with with_empresa_context(pool, empresa_id=1) as conn:
            await conn.execute("SELECT * FROM cliente")  # auto-scoped

    Como funciona:
        - `SET LOCAL app.empresa_id = X` no início da transação.
        - Policies em mig 096 (`_rls_tenant_match`) filtram rows automaticamente.
        - `LOCAL` significa: vale até COMMIT/ROLLBACK; conexão devolvida ao
          pool sem o context (próximo uso começa limpo).

    Bypass (superadmin):
        async with with_empresa_context(pool, None, bypass_rls=True) as conn:
            ...

    Args:
        db_pool: pool do psycopg.
        empresa_id: tenant ID ou None pra bypass.
        bypass_rls: se True, `app.bypass_rls = 'true'` (ignora policies).

    Yields:
        AsyncConnection com transaction aberta + context setado.

    Raises:
        ValueError: se empresa_id None E bypass_rls=False.
    """
    if empresa_id is None and not bypass_rls:
        raise ValueError(
            "with_empresa_context requer empresa_id ou bypass_rls=True."
        )

    async with db_pool.connection() as conn:
        async with conn.transaction():
            # SET LOCAL não aceita parameter binding em psycopg; usa
            # set_config(name, value, is_local) que aceita.
            if bypass_rls:
                await conn.execute(
                    "SELECT set_config('app.bypass_rls', 'true', true)"
                )
            else:
                await conn.execute(
                    "SELECT set_config('app.empresa_id', %s, true)",
                    (str(empresa_id),),
                )
            yield conn


async def run_migrations(db_pool: AsyncConnectionPool) -> None:
    """Aplica migrações SQL pendentes ao banco de dados.

    Lê arquivos de db/migrations/ e aplica os que ainda não foram
    registrados na tabela _migrations.

    Args:
        db_pool: Pool de conexões do psycopg.
    """
    async with db_pool.connection() as conn:
        conn: AsyncConnection
        await _acquire_advisory_lock(conn, MIGRATIONS_LOCK_ID)

        try:
            # Garante que a tabela de controle existe
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id          SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.commit()

            # Busca migrações já aplicadas
            cursor = await conn.execute("SELECT name FROM _migrations ORDER BY name")
            rows = await cursor.fetchall()
            applied = {row[0] for row in rows}

            # Lê e aplica migrações pendentes
            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

            for sql_file in sql_files:
                if sql_file.name in applied:
                    logger.debug("migration_already_applied", migration=sql_file.name)
                    continue

                logger.info("migration_applying", migration=sql_file.name)
                sql = sql_file.read_text(encoding="utf-8")
                await conn.execute(sql.encode())
                await conn.execute(
                    "INSERT INTO _migrations (name) VALUES (%s)",
                    (sql_file.name,),
                )
                await conn.commit()
                logger.info("migration_applied", migration=sql_file.name)
        finally:
            await _release_advisory_lock(conn, MIGRATIONS_LOCK_ID)


def resolve_store_index_config() -> PostgresIndexConfig:
    """Monta configuração de embeddings para o AsyncPostgresStore."""
    api_key = settings.openrouter_api_key
    secret_key = SecretStr(api_key.get_secret_value()) if api_key else None
    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.openrouter_base_url,
        api_key=secret_key,
    )

    return {
        "embed": embeddings,
        "dims": settings.embedding_dims,
        "fields": ["$"],
    }


async def open_checkpointer() -> tuple[AsyncExitStack, AsyncPostgresSaver]:
    """Abre checkpointer PostgreSQL com ciclo de vida explícito."""
    stack = AsyncExitStack()
    checkpointer = await stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(settings.database_url)
    )
    return stack, checkpointer


async def open_store() -> tuple[AsyncExitStack, AsyncPostgresStore] | tuple[None, None]:
    """Abre store vetorial condicionalmente.

    O store só é criado quando MEMORY_ENABLED=true.
    """
    if not settings.memory_enabled:
        logger.info("store_skipped", reason="memory_disabled")
        return None, None

    stack = AsyncExitStack()
    store = await stack.enter_async_context(
        AsyncPostgresStore.from_conn_string(
            settings.database_url,
            index=resolve_store_index_config(),
        )
    )
    return stack, store


async def bootstrap_langgraph_schema() -> None:
    """Inicializa tabelas do checkpointer/store do LangGraph no startup.

    Isso evita criação lazy de schema durante o processamento da primeira
    mensagem e garante que o serviço só entra em estado ready após bootstrap.
    Um advisory lock serializa esse bootstrap entre API e Worker em banco limpo.
    """
    logger.info(
        "langgraph_schema_bootstrap_starting",
        memory_enabled=settings.memory_enabled,
    )
    db_pool = await get_pool()

    async with db_pool.connection() as conn:
        await _acquire_advisory_lock(conn, LANGGRAPH_BOOTSTRAP_LOCK_ID)

        try:
            checkpointer_stack, checkpointer = await open_checkpointer()
            store_stack, store = await open_store()

            try:
                await checkpointer.setup()
                if store is not None:
                    await store.setup()
            finally:
                if store_stack is not None:
                    await store_stack.aclose()
                await checkpointer_stack.aclose()
        finally:
            await _release_advisory_lock(conn, LANGGRAPH_BOOTSTRAP_LOCK_ID)

    logger.info("langgraph_schema_bootstrap_done")


async def check_db_health() -> bool:
    """Verifica se o banco de dados está acessível.

    Executa SELECT 1 para confirmar conectividade.

    Returns:
        True se o banco respondeu, False caso contrário.
    """
    try:
        db_pool = await get_pool()
        async with db_pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("db_health_check_failed", error=str(e))
        return False
