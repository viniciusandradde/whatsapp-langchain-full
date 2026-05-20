"""CRUD + submissão de templates HSM WhatsApp (per-conexão WABA).

Endpoints nestados em /api/conexoes/{conexao_id}/templates/*. Perms:
- waba_template.read: GET list/detail/sync
- waba_template.write: POST create/submit, POST test-send, DELETE, POST import

Sync da Meta: GET /{meta_template_id} retorna status atual + quality_score.
Auto-sync se ultimo_sync_at > 5min ao abrir detalhe.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.waba import templates as waba_templates
from whatsapp_langchain.integrations.waba.models import WabaTemplateRecord
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    get_credentials_decrypted,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/conexoes/{conexao_id}/templates",
    tags=["waba-templates"],
    dependencies=[Depends(verify_service_token)],
)


_TEMPLATE_COLS = (
    "id, empresa_id, conexao_id, nome, categoria, idioma, componentes_json, "
    "status, meta_template_id, meta_quality_score, motivo_rejeicao, "
    "ultimo_sync_at, created_at, updated_at, created_by_user_id"
)


def _row_to_template(row) -> WabaTemplateRecord:
    return WabaTemplateRecord(
        id=row[0],
        empresa_id=row[1],
        conexao_id=row[2],
        nome=row[3],
        categoria=row[4],
        idioma=row[5],
        componentes_json=row[6] or [],
        status=row[7],
        meta_template_id=row[8],
        meta_quality_score=row[9],
        motivo_rejeicao=row[10],
        ultimo_sync_at=row[11],
        created_at=row[12],
        updated_at=row[13],
        created_by_user_id=row[14],
    )


async def _validate_conexao(conexao_id: int, empresa_id: int):
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.provider != "waba":
        raise HTTPException(
            status_code=400, detail="Templates só aplicáveis a conexões WABA."
        )
    return conexao


@router.get("")
async def list_templates(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[WabaTemplateRecord]]:
    await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_TEMPLATE_COLS} FROM waba_template
             WHERE conexao_id = %s AND empresa_id = %s
             ORDER BY id DESC
            """,
            (conexao_id, empresa_id),
        )
        rows = await cur.fetchall()
    return {"templates": [_row_to_template(r) for r in rows]}


class TemplateCreateInput(BaseModel):
    nome: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    categoria: str  # UTILITY | AUTHENTICATION | MARKETING
    idioma: str = "pt_BR"
    componentes_json: list[dict[str, Any]]
    submit: bool = True  # False = só draft, True = também envia pra Meta


@router.post("")
async def create_template(
    conexao_id: int,
    body: TemplateCreateInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> WabaTemplateRecord:
    conexao = await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()

    if body.categoria not in ("UTILITY", "AUTHENTICATION", "MARKETING"):
        raise HTTPException(status_code=422, detail="Categoria inválida.")

    initial_status = "draft"
    meta_id: str | None = None

    if body.submit:
        if not conexao.waba_account_id:
            raise HTTPException(
                status_code=400,
                detail="Conexão sem waba_account_id — não dá pra submeter template.",
            )
        credentials = await get_credentials_decrypted(pool, conexao_id)
        if not credentials or not credentials.get("access_token"):
            raise HTTPException(
                status_code=400, detail="access_token ausente na conexão."
            )
        try:
            result = await waba_templates.submit_template(
                credentials["access_token"],
                conexao.waba_account_id,
                nome=body.nome,
                categoria=body.categoria,
                idioma=body.idioma,
                componentes_json=body.componentes_json,
            )
        except waba_templates.WabaTemplateError as exc:
            raise HTTPException(status_code=502, detail=str(exc.detail)[:300])
        initial_status = "pending"
        meta_id = result.get("id") and str(result["id"])

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO waba_template (
                empresa_id, conexao_id, nome, categoria, idioma,
                componentes_json, status, meta_template_id, created_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (conexao_id, nome, idioma) DO UPDATE SET
                categoria = EXCLUDED.categoria,
                componentes_json = EXCLUDED.componentes_json,
                status = CASE WHEN EXCLUDED.status = 'draft'
                              THEN waba_template.status
                              ELSE EXCLUDED.status END,
                meta_template_id = COALESCE(
                    EXCLUDED.meta_template_id, waba_template.meta_template_id
                ),
                updated_at = NOW()
            RETURNING {_TEMPLATE_COLS}
            """,
            (
                empresa_id,
                conexao_id,
                body.nome,
                body.categoria,
                body.idioma,
                json.dumps(body.componentes_json),
                initial_status,
                meta_id,
                user_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    logger.info(
        "waba_template_created",
        empresa_id=empresa_id,
        conexao_id=conexao_id,
        nome=body.nome,
        status=initial_status,
        meta_id=meta_id,
    )
    return _row_to_template(row)


@router.get("/{template_id}")
async def get_template(
    conexao_id: int,
    template_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> WabaTemplateRecord:
    await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_TEMPLATE_COLS} FROM waba_template
             WHERE id = %s AND conexao_id = %s AND empresa_id = %s
            """,
            (template_id, conexao_id, empresa_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    template = _row_to_template(row)

    # Auto-sync se stale (> 5min) e tem meta_template_id
    if template.meta_template_id and template.status in (
        "pending",
        "approved",
        "paused",
    ):
        stale = (
            template.ultimo_sync_at is None
            or template.ultimo_sync_at
            < datetime.now(template.ultimo_sync_at.tzinfo) - timedelta(minutes=5)
        )
        if stale:
            template = await _sync_template_internal(pool, template) or template

    return template


@router.post("/{template_id}/sync")
async def sync_template(
    conexao_id: int,
    template_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> WabaTemplateRecord:
    """Force-refresh status da Meta."""
    await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_TEMPLATE_COLS} FROM waba_template"
            f" WHERE id = %s AND conexao_id = %s",
            (template_id, conexao_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    template = _row_to_template(row)
    if not template.meta_template_id:
        raise HTTPException(
            status_code=400, detail="Template ainda não submetido (draft)."
        )
    updated = await _sync_template_internal(pool, template)
    return updated or template


async def _sync_template_internal(
    pool, template: WabaTemplateRecord
) -> WabaTemplateRecord | None:
    credentials = await get_credentials_decrypted(pool, template.conexao_id)
    if not credentials or not template.meta_template_id:
        return None
    try:
        data = await waba_templates.sync_template_status(
            credentials["access_token"], template.meta_template_id
        )
    except waba_templates.WabaTemplateError as exc:
        logger.warning(
            "waba_template_sync_failed",
            template_id=template.id,
            error=str(exc.detail)[:200],
        )
        return None

    meta_status = (data.get("status") or "").upper()
    status_map = {
        "PENDING": "pending",
        "APPROVED": "approved",
        "REJECTED": "rejected",
        "PAUSED": "paused",
        "DISABLED": "disabled",
        "FLAGGED": "approved",
    }
    new_status = status_map.get(meta_status, template.status)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE waba_template
               SET status = %s,
                   meta_quality_score = %s,
                   motivo_rejeicao = %s,
                   ultimo_sync_at = NOW(),
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_TEMPLATE_COLS}
            """,
            (
                new_status,
                data.get("quality_score"),
                data.get("rejected_reason"),
                template.id,
            ),
        )
        row = await cur.fetchone()
    return _row_to_template(row) if row else None


class TemplateTestSendInput(BaseModel):
    to_number: str = Field(min_length=8)
    variables: dict[str, str] = Field(default_factory=dict)


@router.post("/{template_id}/test-send")
async def test_send(
    conexao_id: int,
    template_id: int,
    body: TemplateTestSendInput,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Envia template aprovado pra número de teste."""
    conexao = await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_TEMPLATE_COLS} FROM waba_template"
            f" WHERE id = %s AND conexao_id = %s",
            (template_id, conexao_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    template = _row_to_template(row)
    if template.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Template não está aprovado (status={template.status}).",
        )
    credentials = await get_credentials_decrypted(pool, conexao_id)
    if not credentials or not conexao.waba_phone_id:
        raise HTTPException(status_code=400, detail="Credenciais WABA incompletas.")

    try:
        message_id = await waba_templates.send_template_message(
            credentials["access_token"],
            conexao.waba_phone_id,
            to=body.to_number,
            template_name=template.nome,
            language=template.idioma,
            variables=body.variables,
        )
    except waba_templates.WabaTemplateError as exc:
        raise HTTPException(status_code=502, detail=str(exc.detail)[:300])

    return {"ok": True, "message_id": message_id}


@router.delete("/{template_id}", status_code=204)
async def delete_template_endpoint(
    conexao_id: int,
    template_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    conexao = await _validate_conexao(conexao_id, empresa_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT nome FROM waba_template WHERE id = %s AND conexao_id = %s",
            (template_id, conexao_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    nome = row[0]

    # Delete na Meta (best-effort)
    credentials = await get_credentials_decrypted(pool, conexao_id)
    if credentials and conexao.waba_account_id:
        try:
            await waba_templates.delete_template(
                credentials["access_token"], conexao.waba_account_id, nome
            )
        except Exception as exc:
            logger.warning("waba_template_meta_delete_failed", error=str(exc))

    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM waba_template WHERE id = %s",
            (template_id,),
        )
    logger.info("waba_template_deleted", conexao_id=conexao_id, template_id=template_id)


@router.post("/import")
async def import_templates_from_meta(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, int]:
    """Importa templates já aprovados na Meta que não existem no DB local."""
    conexao = await _validate_conexao(conexao_id, empresa_id)
    if not conexao.waba_account_id:
        raise HTTPException(status_code=400, detail="Conexão sem waba_account_id.")
    pool = await get_pool()
    credentials = await get_credentials_decrypted(pool, conexao_id)
    if not credentials:
        raise HTTPException(status_code=400, detail="Credenciais ausentes.")

    try:
        remote = await waba_templates.list_remote_templates(
            credentials["access_token"], conexao.waba_account_id
        )
    except waba_templates.WabaTemplateError as exc:
        raise HTTPException(status_code=502, detail=str(exc.detail)[:300])

    imported = 0
    skipped = 0
    status_map = {
        "PENDING": "pending",
        "APPROVED": "approved",
        "REJECTED": "rejected",
        "PAUSED": "paused",
        "DISABLED": "disabled",
    }

    for t in remote:
        local_status = status_map.get((t.get("status") or "").upper(), "approved")
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO waba_template (
                    empresa_id, conexao_id, nome, categoria, idioma,
                    componentes_json, status, meta_template_id,
                    meta_quality_score, ultimo_sync_at, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NOW(), %s)
                ON CONFLICT (conexao_id, nome, idioma) DO NOTHING
                RETURNING id
                """,
                (
                    empresa_id,
                    conexao_id,
                    t.get("name"),
                    t.get("category"),
                    t.get("language", "pt_BR"),
                    json.dumps(t.get("components", [])),
                    local_status,
                    str(t.get("id", "")),
                    (t.get("quality_score") or {}).get("score")
                    if isinstance(t.get("quality_score"), dict)
                    else None,
                    user_id,
                ),
            )
            row = await cur.fetchone()
        if row:
            imported += 1
        else:
            skipped += 1

    return {"imported": imported, "skipped": skipped, "total_remote": len(remote)}
