"""CRUD genérico de conexões de API (`api_connection`).

Pattern de uso:
    cfgs = await list_conexoes(pool, empresa_id=1)
    new = await create_conexao(pool, empresa_id=1, provider_slug="asaas", ...)
    creds = await get_credenciais(pool, connection_id=42)
    await delete_conexao(pool, connection_id=42)
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.crypto import (
    IntegracaoConfigError,
    decrypt_dict,
    encrypt_dict,
)
from whatsapp_langchain.integrations.providers import (
    get_provider,
    validate_credentials_dict,
)

logger = structlog.get_logger()


def _mask_sensitive(creds: dict, provider_slug: str) -> dict:
    """Substitui campos sensíveis (password/secret) por '••••••••'.
    Usado quando retorna config pro front."""
    provider = get_provider(provider_slug)
    if provider is None:
        return creds
    masked = dict(creds)
    for field in provider.campos:
        if field.sensitive and field.name in masked:
            masked[field.name] = "••••••••"
    return masked


async def list_conexoes(
    pool: AsyncConnectionPool, *, empresa_id: int
) -> list[dict]:
    """Lista conexões da empresa com info enriquecida do provider catalog."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, provider_slug, label, base_url, auth_type, extra_config,
                   ativo, ultimo_teste_at, ultimo_teste_ok, ultimo_teste_erro,
                   created_at, updated_at
              FROM api_connection
             WHERE empresa_id = %s
             ORDER BY ativo DESC, provider_slug ASC, label ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    out: list[dict] = []
    for r in rows:
        provider = get_provider(r[1])
        out.append(
            {
                "id": r[0],
                "provider_slug": r[1],
                "provider_nome": provider.nome if provider else r[1],
                "provider_icone": provider.icone if provider else "Plug",
                "label": r[2],
                "base_url": r[3] or (provider.base_url_default if provider else None),
                "auth_type": r[4],
                "extra_config": r[5] or {},
                "ativo": r[6],
                "ultimo_teste_at": r[7].isoformat() if r[7] else None,
                "ultimo_teste_ok": r[8],
                "ultimo_teste_erro": r[9],
                "created_at": r[10].isoformat() if r[10] else None,
                "updated_at": r[11].isoformat() if r[11] else None,
            }
        )
    return out


async def get_conexao_safe(
    pool: AsyncConnectionPool, *, connection_id: int, empresa_id: int
) -> dict | None:
    """GET com credenciais MASCARADAS (pro front exibir)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, provider_slug, label, base_url, auth_type,
                   credentials_encrypted, extra_config,
                   ativo, ultimo_teste_at, ultimo_teste_ok, ultimo_teste_erro,
                   created_at, updated_at
              FROM api_connection
             WHERE id = %s AND empresa_id = %s
            """,
            (connection_id, empresa_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    creds = decrypt_dict(row[5])
    provider = get_provider(row[1])
    return {
        "id": row[0],
        "provider_slug": row[1],
        "provider_nome": provider.nome if provider else row[1],
        "label": row[2],
        "base_url": row[3] or (provider.base_url_default if provider else None),
        "auth_type": row[4],
        "credentials": _mask_sensitive(creds, row[1]),
        "extra_config": row[6] or {},
        "ativo": row[7],
        "ultimo_teste_at": row[8].isoformat() if row[8] else None,
        "ultimo_teste_ok": row[9],
        "ultimo_teste_erro": row[10],
        "created_at": row[11].isoformat() if row[11] else None,
        "updated_at": row[12].isoformat() if row[12] else None,
    }


async def get_credenciais_decrypted(
    pool: AsyncConnectionPool, *, connection_id: int
) -> dict | None:
    """Retorna credenciais decifradas (use só em handlers de teste e tools)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT credentials_encrypted FROM api_connection WHERE id = %s",
            (connection_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return decrypt_dict(row[0])


async def create_conexao(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    provider_slug: str,
    label: str,
    credentials: dict,
    base_url: str | None = None,
    extra_config: dict | None = None,
    ativo: bool = True,
    created_by_user_id: str | None = None,
) -> dict:
    """Cria conexão. Valida credentials contra schema do provider."""
    provider = get_provider(provider_slug)
    if provider is None:
        raise IntegracaoConfigError(
            f"Provider '{provider_slug}' desconhecido."
        )
    if provider.legacy_storage is not None:
        raise IntegracaoConfigError(
            f"Provider '{provider_slug}' usa storage legacy "
            f"({provider.legacy_storage}) — use a UI dedicada."
        )

    ok, msg = validate_credentials_dict(provider_slug, credentials)
    if not ok:
        raise IntegracaoConfigError(msg or "Credenciais inválidas")

    cred_enc = encrypt_dict(credentials)
    # auth_type vem do provider, exceto Custom (campo dinâmico no creds)
    auth_type = provider.auth_type
    if auth_type == "dynamic":
        auth_method = credentials.get("auth_method") or "none"
        auth_type = (
            "bearer" if auth_method == "bearer"
            else "basic" if auth_method == "basic"
            else "api_key" if auth_method == "api_key_header"
            else "none"
        )

    async with pool.connection() as conn:
        try:
            cur = await conn.execute(
                """
                INSERT INTO api_connection (
                    empresa_id, provider_slug, label, base_url, auth_type,
                    credentials_encrypted, extra_config, ativo,
                    created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    provider_slug,
                    label,
                    base_url or provider.base_url_default,
                    auth_type,
                    cred_enc,
                    "{}" if extra_config is None else _json(extra_config),
                    ativo,
                    created_by_user_id,
                ),
            )
            row = await cur.fetchone()
            await conn.commit()
        except Exception as exc:  # UNIQUE viola
            msg2 = str(exc).lower()
            if "unique" in msg2 or "duplicate" in msg2:
                raise IntegracaoConfigError(
                    f"Já existe conexão {provider_slug} com label '{label}' "
                    "nessa empresa."
                ) from exc
            raise
    assert row is not None
    connection_id = int(row[0])
    logger.info(
        "api_connection_created",
        empresa_id=empresa_id,
        provider=provider_slug,
        label=label,
        connection_id=connection_id,
    )
    detail = await get_conexao_safe(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    assert detail is not None
    return detail


async def update_conexao(
    pool: AsyncConnectionPool,
    *,
    connection_id: int,
    empresa_id: int,
    label: str | None = None,
    base_url: str | None = None,
    credentials_patch: dict | None = None,
    extra_config: dict | None = None,
    ativo: bool | None = None,
) -> dict | None:
    """UPDATE parcial. credentials_patch é mesclado nas credenciais
    existentes (campos vazios = mantém valor anterior — pattern UX
    pra senha)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT provider_slug, credentials_encrypted, base_url
              FROM api_connection
             WHERE id = %s AND empresa_id = %s
            """,
            (connection_id, empresa_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    provider_slug, cred_enc_atual, _ = row

    sets: list[str] = []
    args: list = []
    if label is not None:
        sets.append("label = %s")
        args.append(label)
    if base_url is not None:
        sets.append("base_url = %s")
        args.append(base_url)
    if extra_config is not None:
        sets.append("extra_config = %s::jsonb")
        args.append(_json(extra_config))
    if ativo is not None:
        sets.append("ativo = %s")
        args.append(ativo)

    if credentials_patch:
        # Merge: campos novos sobrescrevem, vazios preservam
        atual = decrypt_dict(cred_enc_atual)
        atual.update({k: v for k, v in credentials_patch.items() if v})
        # Valida só se ainda tem todos os required
        ok, msg = validate_credentials_dict(provider_slug, atual)
        if not ok:
            raise IntegracaoConfigError(msg or "Credenciais inválidas após merge")
        sets.append("credentials_encrypted = %s")
        args.append(encrypt_dict(atual))

    if not sets:
        return await get_conexao_safe(
            pool, connection_id=connection_id, empresa_id=empresa_id
        )

    sets.append("updated_at = NOW()")
    args.extend([connection_id, empresa_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE api_connection SET {', '.join(sets)}
             WHERE id = %s AND empresa_id = %s
             RETURNING id
            """,  # type: ignore[arg-type]
            tuple(args),
        )
        row2 = await cur.fetchone()
        if row2 and credentials_patch:
            # Cripto mudou → limpa token cache
            await conn.execute(
                "DELETE FROM api_connection_token_cache "
                "WHERE connection_id = %s",
                (connection_id,),
            )
        await conn.commit()
    if row2 is None:
        return None
    return await get_conexao_safe(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )


async def delete_conexao(
    pool: AsyncConnectionPool, *, connection_id: int, empresa_id: int
) -> bool:
    """Hard delete. CASCADE limpa token cache."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM api_connection WHERE id = %s AND empresa_id = %s "
            "RETURNING id",
            (connection_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    return row is not None


async def record_test_result(
    pool: AsyncConnectionPool,
    *,
    connection_id: int,
    ok: bool,
    mensagem: str | None,
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE api_connection
               SET ultimo_teste_at = NOW(),
                   ultimo_teste_ok = %s,
                   ultimo_teste_erro = %s,
                   updated_at = NOW()
             WHERE id = %s
            """,
            (ok, mensagem if not ok else None, connection_id),
        )
        await conn.commit()


def _json(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)
