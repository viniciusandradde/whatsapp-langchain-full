"""Ingestão de captura pela extensão Chrome (Task 5 / extensão).

Autenticado por API key (`require_scope("capture")`) — a extensão POSTa os
contatos/grupos raspados do WhatsApp Web. Reusa a camada `shared/captura.py`
(upsert idempotente por `wa_jid` + auditoria em `captura_lote`). O contexto
RLS já é ativado por `verify_api_key`.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import require_scope
from whatsapp_langchain.server.dependencies_plano import assert_plano_feature
from whatsapp_langchain.shared import captura as cap
from whatsapp_langchain.shared.api_key import ApiKeyContext
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.worker.evolution_client import (
    CapturedContact,
    CapturedGroup,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/captura", tags=["captura"])

_MSG_DISPARADOR = (
    "A captura de contatos e grupos faz parte do Disparador, que não está "
    "incluído no seu plano. Faça upgrade para usar."
)

_MAX_BATCH = 2000


class ContatoIn(BaseModel):
    wa_jid: str = Field(min_length=3, max_length=80)
    push_name: str | None = None
    name: str | None = None
    is_business: bool = False
    verified_name: str | None = None


class ContatosBatch(BaseModel):
    contatos: list[ContatoIn] = Field(min_length=1, max_length=_MAX_BATCH)


class GrupoIn(BaseModel):
    wa_group_id: str = Field(min_length=3, max_length=80)
    nome: str | None = None
    descricao: str | None = None
    invite_link: str | None = None
    participantes_count: int = 0


class GruposBatch(BaseModel):
    grupos: list[GrupoIn] = Field(min_length=1, max_length=_MAX_BATCH)


class MembroIn(BaseModel):
    wa_jid: str = Field(min_length=3, max_length=80)
    is_admin: bool = False


class MembrosBatch(BaseModel):
    membros: list[MembroIn] = Field(min_length=1, max_length=_MAX_BATCH)


@router.post("/contatos")
async def ingest_contatos(
    body: ContatosBatch, ctx: ApiKeyContext = Depends(require_scope("capture"))
) -> dict:
    """Upsert idempotente de contatos capturados pela extensão."""
    # ADR-005 leva C1: o Disparador é Pro/Enterprise — a extensão recebe o
    # 402 legível como qualquer outra rota (a empresa vem da API key).
    await assert_plano_feature(ctx.empresa_id, "disparador", mensagem=_MSG_DISPARADOR)
    pool = await get_pool()
    lote_id = await cap.criar_lote(
        pool,
        ctx.empresa_id,
        origem="extensao_chrome",
        tipo="contatos",
        api_key_id=ctx.key_id,
    )
    novos = atualizados = 0
    async with pool.connection() as conn:
        for c in body.contatos:
            payload: CapturedContact = {
                "wa_jid": c.wa_jid,
                "push_name": c.push_name,
                "name": c.name,
                "is_business": c.is_business,
                "verified_name": c.verified_name,
            }
            inserted = await cap.upsert_contato_capturado(
                conn, ctx.empresa_id, payload, lote_id, "extensao_chrome"
            )
            novos += int(inserted)
            atualizados += int(not inserted)
        await conn.commit()
    await cap.finalizar_lote(
        pool,
        lote_id,
        status="concluido",
        recebidos=len(body.contatos),
        novos=novos,
        atualizados=atualizados,
    )
    return {"lote_id": lote_id, "novos": novos, "atualizados": atualizados}


@router.post("/grupos")
async def ingest_grupos(
    body: GruposBatch, ctx: ApiKeyContext = Depends(require_scope("capture"))
) -> dict:
    """Upsert idempotente de grupos capturados pela extensão."""
    # ADR-005 leva C1: o Disparador é Pro/Enterprise — a extensão recebe o
    # 402 legível como qualquer outra rota (a empresa vem da API key).
    await assert_plano_feature(ctx.empresa_id, "disparador", mensagem=_MSG_DISPARADOR)
    pool = await get_pool()
    lote_id = await cap.criar_lote(
        pool,
        ctx.empresa_id,
        origem="extensao_chrome",
        tipo="grupos",
        api_key_id=ctx.key_id,
    )
    novos = 0
    async with pool.connection() as conn:
        for g in body.grupos:
            payload: CapturedGroup = {
                "wa_group_id": g.wa_group_id,
                "nome": g.nome,
                "descricao": g.descricao,
                "invite_link": g.invite_link,
                "participantes_count": g.participantes_count,
                "somos_admin": False,
            }
            _gid, inserted = await cap.upsert_grupo(
                conn, ctx.empresa_id, payload, None, "extensao_chrome"
            )
            novos += int(inserted)
        await conn.commit()
    await cap.finalizar_lote(
        pool, lote_id, status="concluido", recebidos=len(body.grupos), novos=novos
    )
    return {"lote_id": lote_id, "novos": novos}


@router.post("/grupos/{wa_group_id}/membros")
async def ingest_membros(
    wa_group_id: str,
    body: MembrosBatch,
    ctx: ApiKeyContext = Depends(require_scope("capture")),
) -> dict:
    """Upsert de membros de um grupo já capturado (pela extensão)."""
    # ADR-005 leva C1: o Disparador é Pro/Enterprise — a extensão recebe o
    # 402 legível como qualquer outra rota (a empresa vem da API key).
    await assert_plano_feature(ctx.empresa_id, "disparador", mensagem=_MSG_DISPARADOR)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM grupo WHERE empresa_id = %s AND wa_group_id = %s",
            (ctx.empresa_id, wa_group_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(404, "Grupo não capturado ainda")
        grupo_id = int(row[0])
        novos = 0
        for m in body.membros:
            inserted = await cap.upsert_grupo_membro(
                conn, ctx.empresa_id, grupo_id, m.wa_jid, m.is_admin
            )
            novos += int(inserted)
        await conn.commit()
    return {"grupo_id": grupo_id, "novos": novos}
