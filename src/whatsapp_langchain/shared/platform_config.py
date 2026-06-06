"""Config de integrações GLOBAIS da plataforma (não per-empresa).

Tabela `platform_integration_config` (mig 117): credenciais cifradas (Fernet) por
slug. Usado pelo billing (Asaas) com precedência sobre env vars. SEM RLS — o
acesso é protegido pelo gate `is_superadmin` nas rotas; aqui usamos
`empresa_scope(None, bypass=True)` por consistência (tabela não tem empresa_id).
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.crypto import decrypt_dict, encrypt_dict
from whatsapp_langchain.shared.rls_context import empresa_scope


async def get_platform_config(pool: AsyncConnectionPool, slug: str) -> dict | None:
    """Config global cifrada por `slug`, decifrada — ou None se não existir."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT config_encrypted FROM platform_integration_config "
                "WHERE slug = %s",
                (slug,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return decrypt_dict(row[0])


async def set_platform_config(
    pool: AsyncConnectionPool,
    slug: str,
    data: dict,
    *,
    updated_by: str | None = None,
) -> None:
    """Upsert da config global (cifra `data` com Fernet)."""
    ciphertext = encrypt_dict(data)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO platform_integration_config
                    (slug, config_encrypted, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (slug) DO UPDATE
                    SET config_encrypted = EXCLUDED.config_encrypted,
                        updated_at = NOW(),
                        updated_by = EXCLUDED.updated_by
                """,
                (slug, ciphertext, updated_by),
            )
            await conn.commit()
