"""CRUD da tabela `arquivo` (object storage, mig 183).

Único lugar que fala com a tabela de metadados dos objetos. O conteúdo (bytes)
vive no bucket e é manipulado por `shared/storage.py` — aqui só o registro.
Roda sob o contexto RLS do chamador (a tabela tem `tenant_isolation`).
"""

from __future__ import annotations

import json
from typing import Any

from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Arquivo

_COLS = (
    "uuid::text, empresa_id, disk, bucket, object_key, mime_type, "
    "size_bytes, original_name, sha256, thumbnail_key, metadata, created_at"
)


def _row_to_arquivo(row: Any) -> Arquivo:
    metadata = row[10]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return Arquivo(
        uuid=row[0],
        empresa_id=row[1],
        disk=row[2],
        bucket=row[3],
        object_key=row[4],
        mime_type=row[5],
        size_bytes=row[6],
        original_name=row[7],
        sha256=row[8],
        thumbnail_key=row[9],
        metadata=metadata or {},
        created_at=row[11],
    )


async def criar_arquivo(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    disk: str,
    bucket: str,
    object_key: str,
    mime_type: str | None,
    size_bytes: int | None,
    original_name: str | None,
    sha256: str | None,
    metadata: dict | None = None,
) -> Arquivo:
    """Insere o registro do objeto e devolve o `Arquivo` (com o uuid gerado)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO arquivo
                (empresa_id, disk, bucket, object_key, mime_type, size_bytes,
                 original_name, sha256, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_COLS}
            """,
            (
                empresa_id,
                disk,
                bucket,
                object_key,
                mime_type,
                size_bytes,
                original_name,
                sha256,
                json.dumps(metadata or {}),
            ),
        )
        row = await cur.fetchone()
    return _row_to_arquivo(row)


async def get_arquivo(pool: AsyncConnectionPool, uuid: str) -> Arquivo | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM arquivo WHERE uuid = %s", (uuid,)
        )
        row = await cur.fetchone()
    return _row_to_arquivo(row) if row else None


async def delete_arquivo(pool: AsyncConnectionPool, uuid: str) -> bool:
    """Apaga o REGISTRO (não o objeto no bucket — isso é `storage.apagar_midia`)."""
    async with pool.connection() as conn:
        cur = await conn.execute("DELETE FROM arquivo WHERE uuid = %s", (uuid,))
    return cur.rowcount > 0
