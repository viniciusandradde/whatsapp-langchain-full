"""Importer de dataset histórico (Sprint P.5).

Aceita JSONL com formato:
    {"agente_slug": "agendamentos",
     "cliente_msg": "como cancelar?",
     "agente_resposta": "Cancelamento gratuito...",
     "outcome": "success",        # success|transferred|escalated|abandoned
     "csat_nota": 5,               # opcional
     "timestamp": "2025-10-01T..." # opcional}

Popula:
- fewshot_example (status=pending) — vira few-shot quando outcome=success
- rag_query_log (sintético) — pra dashboard ter dados históricos

Pós-import: rodar /api/admin/rag/fewshot/backfill pra gerar embeddings.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/rag/dataset",
    tags=["rag-dataset"],
    dependencies=[Depends(verify_service_token)],
)


class ImportResult(BaseModel):
    received: int
    inserted_fewshot: int
    inserted_querylog: int
    skipped: int
    errors: list[str]


VALID_OUTCOMES = {"success", "transferred", "escalated", "abandoned", "unknown"}


def _parse_jsonl(content: str) -> list[dict[str, Any]]:
    out = []
    for i, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Linha {i}: JSON inválido — {e}",
            ) from e
    return out


def _parse_csv(content: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


@router.post("/import", response_model=ImportResult)
async def import_dataset(
    file: UploadFile = File(...),
    empresa_id: int = Depends(get_empresa_context),
) -> ImportResult:
    """Importa dataset histórico (JSONL ou CSV).

    Detecta formato pelo nome do arquivo. Idempotente via UNIQUE constraint
    indireta (skip se mesmo cliente_msg+agente_slug já existe).
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=422, detail=f"Encoding inválido: {e}"
        ) from e

    fname = (file.filename or "").lower()
    if fname.endswith(".jsonl") or fname.endswith(".ndjson"):
        records = _parse_jsonl(content)
    elif fname.endswith(".csv"):
        records = _parse_csv(content)
    else:
        # Tenta JSONL por default
        records = _parse_jsonl(content)

    pool = await get_pool()
    inserted_fewshot = 0
    inserted_querylog = 0
    skipped = 0
    errors: list[str] = []

    for i, rec in enumerate(records, 1):
        try:
            agente_slug = (rec.get("agente_slug") or "").strip()
            cliente_msg = (rec.get("cliente_msg") or "").strip()
            agente_resposta = (rec.get("agente_resposta") or "").strip()
            outcome = (rec.get("outcome") or "unknown").strip()
            if not agente_slug or not cliente_msg:
                skipped += 1
                continue
            if outcome not in VALID_OUTCOMES:
                outcome = "unknown"

            ts_raw = rec.get("timestamp") or rec.get("created_at")
            ts: datetime | None = None
            if ts_raw:
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    ts = None

            csat = rec.get("csat_nota") or rec.get("csat")
            csat_int = int(csat) if csat is not None and str(csat).strip() else None

            # 1. fewshot_example (só se success com resposta)
            if outcome == "success" and agente_resposta:
                async with pool.connection() as conn:
                    # Skip duplicates por (agente, msg) antigos
                    cur = await conn.execute(
                        """
                        SELECT 1 FROM fewshot_example
                         WHERE empresa_id=%s AND agente_slug=%s
                           AND cliente_msg=%s AND status != 'disabled'
                         LIMIT 1
                        """,
                        (empresa_id, agente_slug, cliente_msg[:1000]),
                    )
                    exists = await cur.fetchone()
                    if not exists:
                        await conn.execute(
                            """
                            INSERT INTO fewshot_example
                              (empresa_id, agente_slug, cliente_msg,
                               agente_resposta, outcome, csat_nota, status,
                               created_at)
                            VALUES (%s, %s, %s, %s, 'success', %s, 'pending',
                                    COALESCE(%s, NOW()))
                            """,
                            (
                                empresa_id, agente_slug,
                                cliente_msg[:1000], agente_resposta[:1500],
                                csat_int, ts,
                            ),
                        )
                        await conn.commit()
                        inserted_fewshot += 1

            # 2. rag_query_log (sintético — sem hits/score, só pra histórico)
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO rag_query_log
                      (empresa_id, query_text, agente_slug, hits, top_score,
                       outcome, mode, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'imported', COALESCE(%s, NOW()))
                    """,
                    (
                        empresa_id, cliente_msg[:500], agente_slug,
                        1 if agente_resposta else 0,
                        None, outcome, ts,
                    ),
                )
                await conn.commit()
                inserted_querylog += 1
        except Exception as e:
            errors.append(f"linha {i}: {str(e)[:200]}")
            if len(errors) > 50:
                errors.append("(mais erros omitidos)")
                break

    logger.info(
        "dataset_imported",
        empresa_id=empresa_id,
        received=len(records),
        fewshot=inserted_fewshot,
        querylog=inserted_querylog,
        skipped=skipped,
        errors=len(errors),
    )

    return ImportResult(
        received=len(records),
        inserted_fewshot=inserted_fewshot,
        inserted_querylog=inserted_querylog,
        skipped=skipped,
        errors=errors,
    )


@router.get("/template")
async def download_template() -> dict:
    """Retorna formato esperado do JSONL pra documentar import."""
    return {
        "format": "JSONL (1 JSON por linha) ou CSV",
        "exemplo_jsonl": (
            '{"agente_slug": "agendamentos", '
            '"cliente_msg": "como cancelar consulta?", '
            '"agente_resposta": "Cancelamento gratuito até 24h antes...", '
            '"outcome": "success", '
            '"csat_nota": 5, '
            '"timestamp": "2025-10-15T14:32:00Z"}'
        ),
        "campos_obrigatorios": ["agente_slug", "cliente_msg"],
        "campos_opcionais": [
            "agente_resposta",
            "outcome (success|transferred|escalated|abandoned|unknown)",
            "csat_nota (1-5)",
            "timestamp (ISO 8601)",
        ],
        "comportamento": {
            "outcome=success E agente_resposta != null": "vira fewshot_example pendente",
            "todos": "viram rag_query_log com mode=imported",
            "duplicate (mesmo cliente_msg+agente_slug)": "ignora",
        },
        "pos_import": "POST /api/admin/rag/fewshot/backfill pra gerar embeddings",
    }
