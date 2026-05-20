"""Storage unificado pra credenciais Google Calendar (Sprint GC migration).

Migra de `empresa_calendar_config` (legacy, JSONB plain text) pra
`api_connection` (genérica, Fernet cripto). Estratégia transição:

- **Read**: api_connection PRIMEIRO, fallback `empresa_calendar_config`
- **Write**: dual-write nos dois (zero risco — outros consumidores
  (horario.py, agendamento.py) continuam lendo do legacy)
- Sprint futura: deletar `empresa_calendar_config` quando estiver
  100% migrado e estável

Provider slug: `google_calendar`. auth_type: `oauth2_web`.
"""

from __future__ import annotations

import json

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.crypto import (
    decrypt_dict,
    encrypt_dict,
)

logger = structlog.get_logger()

PROVIDER_SLUG = "google_calendar"
DEFAULT_LABEL = "Google Calendar"


async def read_unified(pool: AsyncConnectionPool, empresa_id: int) -> dict | None:
    """Lê config Google Calendar — api_connection primeiro, fallback legacy.

    Retorna dict com chaves: oauth_credentials_json (dict descriptografado),
    google_email, calendar_id, timezone, aprovador_telefone, ativo,
    created_at, updated_at. None se não cadastrada em lugar nenhum.
    """
    # 1) Tenta api_connection
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT credentials_encrypted, extra_config, ativo,
                   created_at, updated_at
              FROM api_connection
             WHERE empresa_id = %s AND provider_slug = %s
             LIMIT 1
            """,
            (empresa_id, PROVIDER_SLUG),
        )
        row = await cur.fetchone()
    if row is not None:
        creds_enc, extra, ativo, created_at, updated_at = row
        try:
            oauth = decrypt_dict(creds_enc)
        except Exception as exc:
            logger.warning(
                "google_calendar_decrypt_failed",
                empresa_id=empresa_id,
                error=str(exc),
            )
            oauth = {}
        extra = extra or {}
        return {
            "source": "api_connection",
            "oauth_credentials_json": oauth,
            "google_email": extra.get("google_email"),
            "calendar_id": extra.get("calendar_id") or "primary",
            "timezone": extra.get("timezone") or "America/Sao_Paulo",
            "aprovador_telefone": extra.get("aprovador_telefone"),
            "ativo": ativo,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    # 2) Fallback legacy
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT oauth_credentials_json, google_email, calendar_id,
                   timezone, ativo, aprovador_telefone,
                   created_at, updated_at
              FROM empresa_calendar_config
             WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "source": "empresa_calendar_config",
        "oauth_credentials_json": row[0],  # JSONB já é dict no psycopg3
        "google_email": row[1],
        "calendar_id": row[2],
        "timezone": row[3],
        "ativo": row[4],
        "aprovador_telefone": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }


async def upsert_credentials_dual(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    oauth_credentials_json: dict,
    google_email: str | None,
    created_by_user_id: str | None = None,
) -> None:
    """Salva credenciais OAuth (escreve em AMBOS storages).

    api_connection: credentials_encrypted (Fernet) + extra_config tem
    google_email/calendar_id/timezone.

    empresa_calendar_config: mantida pra compat com horario.py/agendamento.py.
    """
    creds_enc = encrypt_dict(oauth_credentials_json)
    creds_json_str = json.dumps(oauth_credentials_json)

    async with pool.connection() as conn:
        # 1) Lê extra_config existente em api_connection (pra preservar
        # calendar_id/timezone/aprovador setados antes)
        cur = await conn.execute(
            """
            SELECT extra_config FROM api_connection
             WHERE empresa_id = %s AND provider_slug = %s
            """,
            (empresa_id, PROVIDER_SLUG),
        )
        row = await cur.fetchone()
        extra_existente = (row[0] if row else None) or {}

        # 2) Lê config legacy pra preservar calendar_id/timezone etc. na
        # 1ª escrita (quando api_connection ainda não existe)
        if not row:
            cur = await conn.execute(
                """
                SELECT calendar_id, timezone, aprovador_telefone
                  FROM empresa_calendar_config WHERE empresa_id = %s
                """,
                (empresa_id,),
            )
            legacy_row = await cur.fetchone()
            if legacy_row:
                extra_existente.setdefault("calendar_id", legacy_row[0])
                extra_existente.setdefault("timezone", legacy_row[1])
                if legacy_row[2]:
                    extra_existente.setdefault("aprovador_telefone", legacy_row[2])

        extra_existente["google_email"] = google_email
        extra_existente.setdefault("calendar_id", "primary")
        extra_existente.setdefault("timezone", "America/Sao_Paulo")
        extra_json = json.dumps(extra_existente)

        # 3) UPSERT em api_connection
        await conn.execute(
            """
            INSERT INTO api_connection (
                empresa_id, provider_slug, label, base_url, auth_type,
                credentials_encrypted, extra_config, ativo,
                created_by_user_id
            ) VALUES (
                %s, %s, %s, NULL, 'oauth2_web',
                %s, %s::jsonb, TRUE, %s
            )
            ON CONFLICT (empresa_id, provider_slug, label) DO UPDATE SET
                credentials_encrypted = EXCLUDED.credentials_encrypted,
                extra_config = EXCLUDED.extra_config,
                ativo = TRUE,
                updated_at = NOW()
            """,
            (
                empresa_id,
                PROVIDER_SLUG,
                DEFAULT_LABEL,
                creds_enc,
                extra_json,
                created_by_user_id,
            ),
        )

        # 4) Dual-write em empresa_calendar_config (zero risco pra
        # horario.py/agendamento.py)
        await conn.execute(
            """
            INSERT INTO empresa_calendar_config (
                empresa_id, oauth_credentials_json, google_email,
                created_by_user_id, ativo
            )
            VALUES (%s, %s::jsonb, %s, %s, TRUE)
            ON CONFLICT (empresa_id) DO UPDATE SET
                oauth_credentials_json = EXCLUDED.oauth_credentials_json,
                google_email = EXCLUDED.google_email,
                ativo = TRUE,
                updated_at = NOW()
            """,
            (empresa_id, creds_json_str, google_email, created_by_user_id),
        )
        await conn.commit()

    logger.info(
        "google_calendar_creds_dual_write",
        empresa_id=empresa_id,
        email=google_email,
    )


async def refresh_credentials_dual(
    pool: AsyncConnectionPool,
    empresa_id: int,
    oauth_credentials_json: dict,
) -> None:
    """Update do payload OAuth após refresh do token. Mantém metadados."""
    creds_enc = encrypt_dict(oauth_credentials_json)
    creds_json_str = json.dumps(oauth_credentials_json)

    async with pool.connection() as conn:
        # api_connection — só credentials
        await conn.execute(
            """
            UPDATE api_connection
               SET credentials_encrypted = %s,
                   updated_at = NOW()
             WHERE empresa_id = %s AND provider_slug = %s
            """,
            (creds_enc, empresa_id, PROVIDER_SLUG),
        )
        # legacy
        await conn.execute(
            """
            UPDATE empresa_calendar_config
               SET oauth_credentials_json = %s::jsonb,
                   updated_at = NOW()
             WHERE empresa_id = %s
            """,
            (creds_json_str, empresa_id),
        )
        await conn.commit()


async def update_setting_dual(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    calendar_id: str | None = None,
    timezone: str | None = None,
    aprovador_telefone: str | None = None,
) -> bool:
    """UPDATE parcial de metadados (calendar_id, timezone, aprovador).

    api_connection.extra_config (merge JSONB) + colunas em
    empresa_calendar_config. Retorna True se algo foi atualizado.
    """
    updates: dict = {}
    if calendar_id is not None:
        updates["calendar_id"] = calendar_id
    if timezone is not None:
        updates["timezone"] = timezone
    if aprovador_telefone is not None:
        # String vazia → None (remove)
        updates["aprovador_telefone"] = aprovador_telefone or None
    if not updates:
        return False

    async with pool.connection() as conn:
        # 1) api_connection — merge JSONB
        await conn.execute(
            """
            UPDATE api_connection
               SET extra_config = extra_config || %s::jsonb,
                   updated_at = NOW()
             WHERE empresa_id = %s AND provider_slug = %s
            """,
            (json.dumps(updates), empresa_id, PROVIDER_SLUG),
        )
        # 2) empresa_calendar_config — colunas tradicionais
        legacy_sets: list[str] = []
        legacy_args: list = []
        if calendar_id is not None:
            legacy_sets.append("calendar_id = %s")
            legacy_args.append(calendar_id)
        if timezone is not None:
            legacy_sets.append("timezone = %s")
            legacy_args.append(timezone)
        if aprovador_telefone is not None:
            legacy_sets.append("aprovador_telefone = %s")
            legacy_args.append(aprovador_telefone or None)
        if legacy_sets:
            legacy_sets.append("updated_at = NOW()")
            legacy_args.append(empresa_id)
            await conn.execute(
                f"""
                UPDATE empresa_calendar_config SET {", ".join(legacy_sets)}
                 WHERE empresa_id = %s
                """,  # type: ignore[arg-type]
                tuple(legacy_args),
            )
        await conn.commit()
    return True


async def delete_dual(pool: AsyncConnectionPool, empresa_id: int) -> bool:
    """DELETE em AMBOS storages (cascade no token_cache via FK).

    Retorna True se ao menos um deletou.
    """
    async with pool.connection() as conn:
        cur1 = await conn.execute(
            """
            DELETE FROM api_connection
             WHERE empresa_id = %s AND provider_slug = %s
             RETURNING id
            """,
            (empresa_id, PROVIDER_SLUG),
        )
        n1 = await cur1.fetchall()
        cur2 = await conn.execute(
            "DELETE FROM empresa_calendar_config WHERE empresa_id = %s "
            "RETURNING empresa_id",
            (empresa_id,),
        )
        n2 = await cur2.fetchall()
        await conn.commit()
    return bool(n1) or bool(n2)


async def migrate_legacy_to_api_connection(
    pool: AsyncConnectionPool,
) -> dict:
    """One-shot: copia rows empresa_calendar_config → api_connection.

    Idempotente: skip empresas que já têm api_connection google_calendar.
    Retorna {migrated: int, skipped: int, total_legacy: int}.
    """
    migrated = 0
    skipped = 0
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT ecc.empresa_id, ecc.oauth_credentials_json,
                   ecc.google_email, ecc.calendar_id, ecc.timezone,
                   ecc.aprovador_telefone, ecc.ativo, ecc.created_by_user_id
              FROM empresa_calendar_config ecc
             WHERE NOT EXISTS (
                 SELECT 1 FROM api_connection ac
                  WHERE ac.empresa_id = ecc.empresa_id
                    AND ac.provider_slug = %s
             )
            """,
            (PROVIDER_SLUG,),
        )
        rows = await cur.fetchall()
        total_legacy = len(rows)

    for r in rows:
        (
            empresa_id,
            oauth_json,
            email,
            calendar_id,
            timezone,
            aprovador,
            ativo,
            created_by,
        ) = r
        # oauth_json vem dict (JSONB)
        if not isinstance(oauth_json, dict):
            try:
                oauth_json = json.loads(oauth_json)
            except Exception:
                logger.warning("migration_skip_invalid_json", empresa_id=empresa_id)
                skipped += 1
                continue
        creds_enc = encrypt_dict(oauth_json)
        extra = {
            "google_email": email,
            "calendar_id": calendar_id or "primary",
            "timezone": timezone or "America/Sao_Paulo",
        }
        if aprovador:
            extra["aprovador_telefone"] = aprovador
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO api_connection (
                    empresa_id, provider_slug, label, auth_type,
                    credentials_encrypted, extra_config, ativo,
                    created_by_user_id
                ) VALUES (%s, %s, %s, 'oauth2_web', %s, %s::jsonb, %s, %s)
                ON CONFLICT (empresa_id, provider_slug, label) DO NOTHING
                """,
                (
                    empresa_id,
                    PROVIDER_SLUG,
                    DEFAULT_LABEL,
                    creds_enc,
                    json.dumps(extra),
                    ativo,
                    created_by,
                ),
            )
            await conn.commit()
        migrated += 1
        logger.info(
            "google_calendar_migrated_to_api_connection",
            empresa_id=empresa_id,
            email=email,
        )

    return {
        "migrated": migrated,
        "skipped": skipped,
        "total_legacy": total_legacy,
    }
