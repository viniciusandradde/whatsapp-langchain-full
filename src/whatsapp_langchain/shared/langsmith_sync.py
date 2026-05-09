"""LangSmith dataset sync — Sprint T.1.

Espelha fewshot_example (sandbox) → dataset LangSmith. Cópia, não migração:
fewshot_example continua sendo a fonte de verdade local; LangSmith vira
mirror externo pra análise + eval.

Idempotente via metadata.fewshot_id (re-runs SKIP existentes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)


DEFAULT_DATASET_NAME = "mackenzie-hospital-atendimento-sandbox"
BATCH_SIZE = 200


@dataclass
class SyncResult:
    dataset_id: str
    dataset_url: str
    total_db: int
    already_synced: int
    created: int
    errors: list[str] = field(default_factory=list)


def _build_example(
    *,
    cliente_msg: str,
    agente_resposta: str,
    setor: str | None,
    agente_slug: str,
    fewshot_id: int,
    outcome: str | None,
    csat_nota: int | None,
) -> dict:
    """Normaliza fewshot pra schema LangSmith Example."""
    return {
        "inputs": {
            "cliente_msg": cliente_msg,
            "setor": setor or "atendimento",
            "agente_slug": agente_slug,
        },
        "outputs": {
            "agente_resposta_esperada": agente_resposta,
        },
        "metadata": {
            "fewshot_id": fewshot_id,
            "outcome": outcome or "unknown",
            "csat_nota": csat_nota,
            "source": "sandbox_999",
            "imported_at": datetime.now(UTC).isoformat(),
        },
    }


async def _fetch_fewshots(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    filter_success: bool,
) -> list[dict]:
    """Lê fewshot_example com filtros aplicados."""
    where = ["empresa_id = %s", "status != 'disabled'"]
    params: list[Any] = [empresa_id]
    if filter_success:
        where.append("outcome = 'success'")
    sql = f"""
        SELECT id, agente_slug, cliente_msg, agente_resposta,
               outcome, csat_nota, setor_classificado
          FROM fewshot_example
         WHERE {" AND ".join(where)}
         ORDER BY id ASC
    """
    from psycopg import sql as _sql

    async with pool.connection() as conn:
        cur = await conn.execute(_sql.SQL(sql), tuple(params))  # type: ignore[arg-type]
        rows = await cur.fetchall()
    return [
        {
            "fewshot_id": int(r[0]),
            "agente_slug": r[1],
            "cliente_msg": r[2],
            "agente_resposta": r[3],
            "outcome": r[4],
            "csat_nota": r[5],
            "setor": r[6],
        }
        for r in rows
    ]


def _ensure_dataset(client, name: str, description: str):
    """Idempotente: usa dataset existente ou cria novo."""
    try:
        ds = client.read_dataset(dataset_name=name)
        logger.info("langsmith_dataset_exists id=%s", ds.id)
        return ds
    except Exception:
        # Não existe — cria
        ds = client.create_dataset(dataset_name=name, description=description)
        logger.info("langsmith_dataset_created id=%s", ds.id)
        return ds


def _existing_fewshot_ids(client, dataset_id: str) -> set[int]:
    """Lê metadata.fewshot_id de exemplos já sincronizados."""
    seen: set[int] = set()
    try:
        for ex in client.list_examples(dataset_id=dataset_id):
            md = ex.metadata or {}
            fid = md.get("fewshot_id")
            if fid is not None:
                try:
                    seen.add(int(fid))
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        logger.warning("langsmith_list_examples_failed: %s", e)
    return seen


async def sync_to_langsmith(
    pool: AsyncConnectionPool,
    *,
    api_key: str,
    empresa_id: int = 999,
    dataset_name: str = DEFAULT_DATASET_NAME,
    filter_success: bool = False,
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
) -> SyncResult:
    """Pipeline completo de sincronização.

    Idempotente: re-runs só inserem fewshots novos (via metadata.fewshot_id).
    """
    from langsmith import Client  # import lazy (não obrigatório carregar)

    client = Client(api_key=api_key)
    description = (
        f"Mirror dos fewshots sandbox empresa {empresa_id} "
        f"({'só success' if filter_success else 'todos status'}). "
        f"Fonte de verdade continua em fewshot_example."
    )

    # 1. Garante dataset
    dataset = (
        _ensure_dataset(client, dataset_name, description) if not dry_run else None
    )
    dataset_id = str(dataset.id) if dataset else "(dry-run)"

    # 2. Lê fewshots do DB
    rows = await _fetch_fewshots(
        pool, empresa_id=empresa_id, filter_success=filter_success
    )
    total_db = len(rows)

    # 3. Filtra já sincronizados
    already = _existing_fewshot_ids(client, dataset_id) if dataset else set()
    pending = [r for r in rows if r["fewshot_id"] not in already]

    logger.info(
        "langsmith_sync_plan total_db=%d already=%d pending=%d dry_run=%s",
        total_db,
        len(already),
        len(pending),
        dry_run,
    )

    if dry_run:
        return SyncResult(
            dataset_id="(dry-run)",
            dataset_url="(dry-run)",
            total_db=total_db,
            already_synced=len(already),
            created=0,
        )

    # 4. Bulk create em batches
    created = 0
    errors: list[str] = []
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        examples = [
            _build_example(
                cliente_msg=r["cliente_msg"],
                agente_resposta=r["agente_resposta"],
                setor=r["setor"],
                agente_slug=r["agente_slug"],
                fewshot_id=r["fewshot_id"],
                outcome=r["outcome"],
                csat_nota=r["csat_nota"],
            )
            for r in batch
        ]
        try:
            client.create_examples(dataset_id=dataset_id, examples=examples)
            created += len(examples)
            logger.info(
                "langsmith_batch_ok start=%d batch=%d total_created=%d",
                i,
                len(batch),
                created,
            )
        except Exception as e:
            err = f"batch starting at {i}: {str(e)[:200]}"
            errors.append(err)
            logger.warning("langsmith_batch_failed %s", err)
            if len(errors) > 10:
                break

    dataset_url = f"https://smith.langchain.com/datasets/{dataset_id}"
    return SyncResult(
        dataset_id=dataset_id,
        dataset_url=dataset_url,
        total_db=total_db,
        already_synced=len(already),
        created=created,
        errors=errors,
    )
