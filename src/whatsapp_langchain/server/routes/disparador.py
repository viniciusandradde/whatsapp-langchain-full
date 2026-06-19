"""Endpoints do Disparador consumidos pela extensão Chrome (Task 2).

Diferente dos demais routers admin (autenticados por `verify_service_token` +
header de empresa), estes endpoints autenticam pela **API key por empresa**
(`verify_api_key`), que descobre a empresa pela própria chave e ativa o
contexto RLS. A extensão usa SOMENTE este caminho — nunca o token de serviço.
"""

from __future__ import annotations

import re

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import require_scope, verify_api_key
from whatsapp_langchain.shared import campanha as camp_lib
from whatsapp_langchain.shared.api_key import ApiKeyContext
from whatsapp_langchain.shared.conexao import get_conexao_by_id, list_conexoes
from whatsapp_langchain.shared.db import get_pool


def _suporta_template(provider: str | None) -> bool:
    """WABA (Meta) e Twilio têm template HSM; Evolution não."""
    return provider == "waba" or (provider or "").startswith("twilio")


logger = structlog.get_logger()

router = APIRouter(prefix="/api/disparador", tags=["disparador"])


@router.get("/status")
async def get_status(ctx: ApiKeyContext = Depends(verify_api_key)) -> dict:
    """Health-check autenticado: a extensão usa pra validar a API key + URL.

    Retorna a empresa resolvida e os escopos da chave (sem expor segredo).
    """
    return {
        "ok": True,
        "empresa_id": ctx.empresa_id,
        "scopes": ctx.scopes,
        "rate_limit_per_minute": ctx.rate_limit_per_minute,
    }


# ---- Disparo in-browser (extensão ZDG-clone, híbrido) ----
# A extensão envia via WPPConnect no navegador e reporta os acks aqui pra que o
# /campanhas mostre histórico/progresso. Campanhas origem_envio='extensao' NÃO
# são pegas pelo dispatcher/poller do backend.


class ExtCampanhaInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    mensagem: str | None = Field(default=None, max_length=4000)
    telefones: list[str] = Field(min_length=1, max_length=10_000)


class ExtReportItem(BaseModel):
    telefone: str
    status: str  # 'enviado' | 'falhou'
    erro: str | None = None
    wamid: str | None = None


class ExtReportInput(BaseModel):
    items: list[ExtReportItem] = Field(min_length=1, max_length=2000)


@router.post("/ext/campanha", status_code=201)
async def ext_criar_campanha(
    body: ExtCampanhaInput,
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Cria uma campanha origem_envio='extensao' (status 'running') pro disparo
    in-browser. Retorna o id + os destinatários normalizados pra enviar."""
    pool = await get_pool()
    try:
        camp = await camp_lib.create_campanha(
            pool,
            ctx.empresa_id,
            nome=body.nome,
            descricao=None,
            mensagem=body.mensagem,
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=10_000,
            telefones_brutos=body.telefones,
            user_id=None,
            origem_envio="extensao",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    destinatarios = await camp_lib.list_destinatarios(pool, camp["id"], limit=10_000)
    return {
        "campanha_id": camp["id"],
        "total": camp["total_destinatarios"],
        "telefones": [d["telefone"] for d in destinatarios],
    }


# ---- Canal oficial (WABA/Twilio) pela extensão — roteado pelo backend ----
# A extensão NÃO chama a Graph API direto (sem token Meta no browser). Reusa a
# conexão WABA do painel + templates aprovados; o dispatcher do backend envia.


class ExtCampanhaTemplateInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    conexao_id: int
    message_template_id: int
    template_variaveis: dict[str, str] = Field(default_factory=dict)
    telefones: list[str] = Field(min_length=1, max_length=10_000)
    scheduled_at: str | None = None


@router.get("/ext/conexoes")
async def ext_conexoes(
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Conexões oficiais (WABA/Twilio) ativas da empresa, pro seletor da extensão."""
    pool = await get_pool()
    conns = await list_conexoes(pool, ctx.empresa_id)
    items = [
        {
            "id": c.id,
            "display_name": c.display_name,
            "from_number": c.from_number,
            "provider": c.provider,
        }
        for c in conns
        if c.status == "active" and _suporta_template(c.provider)
    ]
    return {"items": items}


@router.get("/ext/templates")
async def ext_templates(
    conexao_id: int,
    ctx: ApiKeyContext = Depends(require_scope("templates")),
) -> dict:
    """Templates aprovados da conexão + variáveis inferidas ({{1}},{{2}}…)."""
    pool = await get_pool()
    conn = await get_conexao_by_id(pool, conexao_id)
    if conn is None or conn.empresa_id != ctx.empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    async with pool.connection() as c:
        cur = await c.execute(
            """
            SELECT id, nome, idioma, componentes_json FROM waba_template
             WHERE conexao_id = %s AND empresa_id = %s AND status = 'approved'
             ORDER BY id DESC
            """,
            (conexao_id, ctx.empresa_id),
        )
        rows = await cur.fetchall()
    items = []
    for r in rows:
        corpo = ""
        for comp in r[3] or []:
            if (comp.get("type") or "").upper() == "BODY":
                corpo = str(comp.get("text") or "")
                break
        variaveis = sorted(set(re.findall(r"\{\{(\d+)\}\}", corpo)), key=int)
        items.append(
            {
                "id": r[0],
                "nome": r[1],
                "idioma": r[2],
                "corpo": corpo,
                "variaveis": variaveis,
            }
        )
    return {"items": items}


@router.post("/ext/campanha-template", status_code=201)
async def ext_campanha_template(
    body: ExtCampanhaTemplateInput,
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Cria campanha com template HSM numa conexão oficial e dispara pelo backend.

    Sem `scheduled_at` → despacha já (fire-and-forget). Com `scheduled_at` →
    agendada (o poller do backend envia na hora marcada)."""
    pool = await get_pool()
    conn = await get_conexao_by_id(pool, body.conexao_id)
    if conn is None or conn.empresa_id != ctx.empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if not _suporta_template(conn.provider):
        raise HTTPException(
            status_code=400,
            detail="Conexão não suporta templates (use WhatsApp Oficial/WABA ou Twilio).",
        )
    async with pool.connection() as c:
        cur = await c.execute(
            """
            SELECT 1 FROM waba_template
             WHERE id = %s AND conexao_id = %s AND empresa_id = %s AND status = 'approved'
            """,
            (body.message_template_id, body.conexao_id, ctx.empresa_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Template não encontrado ou não aprovado nesta conexão.",
            )
    agendar = bool(body.scheduled_at)
    try:
        camp = await camp_lib.create_campanha(
            pool,
            ctx.empresa_id,
            nome=body.nome,
            descricao=None,
            mensagem=None,
            conexao_id=body.conexao_id,
            intervalo_ms=500,
            max_destinatarios=10_000,
            telefones_brutos=body.telefones,
            user_id=None,
            message_template_id=body.message_template_id,
            template_variaveis=body.template_variaveis or None,
            scheduled_at=body.scheduled_at,
            agendar=agendar,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Campanha nasce 'draft'; sem agendamento, despacha agora (poller pega as agendadas).
    if not agendar:
        camp_lib.schedule_dispatch(pool, ctx.empresa_id, camp["id"])
    logger.info(
        "ext_campanha_template_criada",
        empresa_id=ctx.empresa_id,
        campanha_id=camp["id"],
        conexao_id=body.conexao_id,
        agendada=agendar,
    )
    return {
        "campanha_id": camp["id"],
        "total": camp["total_destinatarios"],
        "agendada": agendar,
    }


@router.post("/ext/campanha/{camp_id}/report")
async def ext_report(
    camp_id: int,
    body: ExtReportInput,
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Aplica o reporte de envio in-browser (acks por destinatário)."""
    pool = await get_pool()
    try:
        return await camp_lib.aplicar_report_ext(
            pool, ctx.empresa_id, camp_id, [i.model_dump() for i in body.items]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
