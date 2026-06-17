"""Endpoints de Campanha (E2.D M6.b).

CRUD + dispatch + abort. Dispatch é fire-and-forget — handler retorna
202 e o background task atualiza progresso no DB.
"""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared import campanha as camp_lib
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

# Mídia de campanha (foto) — mesmo padrão de avatars/logos (volume Docker
# disparador_media:/app/uploads/disparador). Servida em /uploads/disparador.
_MEDIA_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_MEDIA_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_DISPARADOR_MEDIA_DIR = Path(
    os.environ.get("DISPARADOR_MEDIA_DIR", "/app/uploads/disparador")
)
try:
    _DISPARADOR_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError):
    _DISPARADOR_MEDIA_DIR = Path.cwd() / "uploads" / "disparador"
    _DISPARADOR_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(
    prefix="/api/campanhas",
    tags=["campanha"],
    dependencies=[Depends(verify_service_token)],
)


class CampanhaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    # Texto livre (só dentro da janela 24h) OU template (message_template_id).
    mensagem: str | None = Field(default=None, max_length=4000)
    conexao_id: int | None = None
    intervalo_ms: int = Field(default=500, ge=0, le=60_000)
    max_destinatarios: int = Field(default=1000, ge=1, le=10_000)
    # Lista crua (será normalizada em E.164 no helper)
    telefones: list[str] = Field(min_length=1, max_length=10_000)
    # Sub-fase B+ (padrão profissional) (mig 051)
    modelo_mensagem_id: int | None = None
    scheduled_at: str | None = None  # ISO datetime
    tipo: str = "broadcast"  # broadcast|transactional|reativacao
    filtro_segmento: str | None = Field(default=None, max_length=120)
    filtro_tags: list[str] | None = None
    # Template HSM (mig 113) — broadcast fora da janela 24h
    message_template_id: int | None = None
    template_variaveis: dict[str, str] = Field(default_factory=dict)
    # Anti-ban (migs 120/121) — jitter aleatório + kill-switch
    intervalo_min_ms: int | None = Field(default=None, ge=0, le=600_000)
    intervalo_max_ms: int | None = Field(default=None, ge=0, le=600_000)
    kill_switch_pct: int | None = Field(default=None, ge=0, le=100)
    # Mídia (mig 123) — foto; mensagem vira legenda
    media_url: str | None = Field(default=None, max_length=1000)
    media_tipo: str | None = None

    @model_validator(mode="after")
    def _texto_ou_template(self) -> CampanhaCreate:
        if (
            not self.message_template_id
            and not self.media_url
            and not (self.mensagem or "").strip()
        ):
            raise ValueError(
                "Informe `mensagem` (texto), `media_url` (foto) OU `message_template_id`."
            )
        if self.media_tipo is not None and self.media_tipo not in {
            "image",
            "video",
            "document",
        }:
            raise ValueError("media_tipo deve ser image, video ou document.")
        if (
            self.intervalo_min_ms is not None
            and self.intervalo_max_ms is not None
            and self.intervalo_min_ms > self.intervalo_max_ms
        ):
            raise ValueError(
                "intervalo_min_ms não pode ser maior que intervalo_max_ms."
            )
        return self


@router.get("")
async def list_campanhas_endpoint(
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    items = await camp_lib.list_campanhas(pool, empresa_id)
    return {"items": items}


@router.get("/{camp_id}")
async def get_campanha_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    return out


@router.get("/{camp_id}/destinatarios")
async def list_dest_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
    limit: int = 200,
) -> dict:
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    items = await camp_lib.list_destinatarios(pool, camp_id, limit=limit)
    return {"items": items}


@router.post("", status_code=201)
async def create_endpoint(
    body: CampanhaCreate,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    pool = await get_pool()
    try:
        out = await camp_lib.create_campanha(
            pool,
            empresa_id,
            nome=body.nome,
            descricao=body.descricao,
            mensagem=body.mensagem,
            conexao_id=body.conexao_id,
            intervalo_ms=body.intervalo_ms,
            max_destinatarios=body.max_destinatarios,
            telefones_brutos=body.telefones,
            user_id=user_id,
            # Sub-fase B+ (padrão profissional) (mig 051)
            modelo_mensagem_id=body.modelo_mensagem_id,
            scheduled_at=body.scheduled_at,
            tipo=body.tipo,
            filtro_segmento=body.filtro_segmento,
            filtro_tags=body.filtro_tags,
            message_template_id=body.message_template_id,
            template_variaveis=body.template_variaveis,
            intervalo_min_ms=body.intervalo_min_ms,
            intervalo_max_ms=body.intervalo_max_ms,
            kill_switch_pct=body.kill_switch_pct,
            media_url=body.media_url,
            media_tipo=body.media_tipo,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return out


@router.post("/upload-media", status_code=201)
async def upload_media_endpoint(
    file: UploadFile = File(...),
    empresa_id: int = Depends(get_empresa_context),
    _perm: None = Depends(require_permission("disparador.disparar")),
) -> dict:
    """Upload de foto pra campanha. Valida MIME+tamanho, re-encoda via Pillow
    (nunca confia no MIME do client), salva em DISPARADOR_MEDIA_DIR e devolve
    `media_url` (path relativo /uploads/disparador/...) + `media_tipo`."""
    content = await file.read()
    if len(content) > _MEDIA_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {_MEDIA_MAX_BYTES // 1024 // 1024} MB.",
        )
    if file.content_type not in _MEDIA_MIMES:
        raise HTTPException(
            status_code=415, detail="Formato não suportado. Use PNG, JPEG, WebP ou GIF."
        )
    try:
        from PIL import Image
    except ImportError as e:
        raise HTTPException(503, "Pillow não disponível no servidor.") from e
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))
        # Limita dimensão máxima (anti-payload gigante) mantendo aspecto.
        img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    except Exception as e:
        raise HTTPException(422, f"Imagem inválida: {e}") from e

    fname = f"{empresa_id}_{uuid.uuid4().hex}.jpg"
    _DISPARADOR_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    img.save(_DISPARADOR_MEDIA_DIR / fname, format="JPEG", quality=85, optimize=True)
    return {"media_url": f"/uploads/disparador/{fname}", "media_tipo": "image"}


@router.post("/{camp_id}/dispatch", status_code=202)
async def dispatch_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Inicia envio em background. Retorna 202 imediatamente.

    Idempotência: dispatch só atua em campanha 'draft'. Chamadas
    repetidas em campanha 'running' são no-op (mas retornam 200 no
    background task helper). Pra reenviar pendentes/falhos, use
    endpoint dedicado (TODO).
    """
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    if out["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Campanha em status {out['status']!r} — só draft pode ser despachado."
            ),
        )
    camp_lib.schedule_dispatch(pool, empresa_id, camp_id)
    logger.info("campanha_dispatch_scheduled", camp_id=camp_id, empresa_id=empresa_id)
    return {"ok": True, "campanha_id": camp_id, "status": "queued"}


@router.post("/{camp_id}/abort", status_code=200)
async def abort_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    ok = await camp_lib.abort_campanha(pool, empresa_id, camp_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Campanha não está em draft/running.",
        )
    return {"ok": True}
