"""Sprint U.3 — endpoints CRUD completo de usuários da empresa.

Substitui (em vez de remover) `/api/empresas/{id}/membros` como
caminho preferido — UI nova /usuarios chama estes endpoints.

Auth: `empresa.member.add` perm (admin de empresa OR superadmin).

Endpoints:
- GET    /api/usuarios              — lista enriquecida com filtros
- GET    /api/usuarios/{user_id}    — detalhe
- POST   /api/usuarios              — criar (Better Auth.user + membership)
- PUT    /api/usuarios/{user_id}    — atualizar (nome, telefone, perfis, deptos)
- POST   /api/usuarios/{user_id}/avatar — upload imagem
- POST   /api/usuarios/{user_id}/sessions/invalidate — força re-login (após reset senha)
- GET    /api/usuarios/exists/{user_id} — confirma existência (pra reset Server Action)
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, model_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_plano import require_plano_limit
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.atendimento import (
    list_atendimentos,
    transfer_atendimento,
    transfer_atendimento_to_departamento,
)
from whatsapp_langchain.shared.audit_governanca import (
    list_audit_governanca,
    record_audit_governanca,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import set_user_status
from whatsapp_langchain.shared.telefone import normalizar_br
from whatsapp_langchain.shared.usuarios import (
    TenantValidationError,
    atualizar_usuario,
    contar_admins_empresa,
    criar_usuario_completo,
    get_role_legacy,
    get_usuario,
    invalidar_sessions,
    list_usuarios_da_empresa,
    remover_usuario_da_empresa,
    replicar_usuario,
    resolve_user_names,
    set_avatar_path,
    verificar_user_existe,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("/me/tour")
async def read_meu_tour(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """O usuário já viu o guia de primeiro acesso? (mig 171)

    Sem permissão específica de propósito: é preferência do PRÓPRIO usuário,
    mesmo padrão do `me-status` do atendente. Falhar aqui não pode travar o
    painel — o frontend trata erro como "já viu" e segue.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT tour_operador_at FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
    return {"visto": bool(row and row[0])}


@router.post("/me/tour")
async def marcar_meu_tour(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Marca o guia como visto (concluído OU dispensado — dá no mesmo).

    Idempotente: `COALESCE` preserva a primeira data, então rever o guia no
    futuro não reescreve quando a pessoa viu pela primeira vez.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            'UPDATE auth."user" '
            "SET tour_operador_at = COALESCE(tour_operador_at, NOW()) "
            "WHERE id = %s",
            (user_id,),
        )
    logger.info("tour_operador_visto", actor_user_id=user_id)
    return {"ok": True}


_AVATARS_DIR = Path(os.environ.get("AVATARS_DIR", "/app/uploads/avatars"))
_AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _avatar_safe_id(user_id: str) -> str:
    """Sanitiza user_id pra filename (evita path traversal)."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id)[:64]


def _delete_avatar_file(user_id: str) -> None:
    """Remove o arquivo de avatar local (best-effort)."""
    try:
        (_AVATARS_DIR / f"{_avatar_safe_id(user_id)}.png").unlink(missing_ok=True)
    except OSError:
        logger.warning("avatar_unlink_failed", user_id=user_id)


def _telefone_normalizado_ou_400(raw: str | None) -> str | None:
    """Telefone completo (+55 DDD linha) ou 400 com frase legível.

    Antes disso o campo aceitava qualquer texto de até 30 chars, gravado cru —
    e a empresa 1 ficou um mês com o relatório mensal falhando porque o número
    cadastrado não tinha DDD. Telefone de usuário é destino de WhatsApp
    (convite de acesso, avisos): ou está completo, ou é recusado na entrada.

    Vazio/None passa como None — telefone continua opcional; obrigatório é só
    quando o admin pede o envio do convite.
    """
    if raw is None or not raw.strip():
        return None
    tel = normalizar_br(raw)
    if tel is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Telefone incompleto ou inválido. Informe com DDD, no formato "
                "+5567999990000 — é para esse número que o convite de acesso "
                "e os avisos são enviados."
            ),
        )
    return tel


# Pydantic models


class ConexaoAssign(BaseModel):
    id: int
    is_default: bool = False


class CreateUsuarioInput(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=30)
    role_legacy: str = Field(default="operator", pattern=r"^(admin|operator|viewer)$")
    perfis_ids: list[int] = Field(default_factory=list)
    departamentos_ids: list[int] = Field(default_factory=list)
    conexoes: list[ConexaoAssign] | None = None
    atendente_max_paralelos: int | None = Field(default=None, ge=1, le=50)


class UpdateUsuarioInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=30)
    role_legacy: str | None = Field(default=None, pattern=r"^(admin|operator|viewer)$")
    perfis_ids: list[int] | None = None
    departamentos_ids: list[int] | None = None
    conexoes: list[ConexaoAssign] | None = None


class StatusUsuarioInput(BaseModel):
    status: str = Field(pattern=r"^(active|disabled)$")
    # Ao desabilitar, o que fazer com atendimentos abertos do user:
    on_disable: str = Field(default="none", pattern=r"^(reassign|departamento|none)$")
    target_user_id: str | None = None
    departamento_id: int | None = None

    @model_validator(mode="after")
    def _check_transfer_target(self) -> StatusUsuarioInput:
        if self.status != "disabled":
            return self
        if self.on_disable == "reassign" and not self.target_user_id:
            raise ValueError("on_disable=reassign exige target_user_id.")
        if self.on_disable == "departamento" and not self.departamento_id:
            raise ValueError("on_disable=departamento exige departamento_id.")
        return self


class ReplicarUsuarioInput(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=30)


class ConviteInput(BaseModel):
    """Link de definição de senha gerado pelo Better Auth no frontend.

    O link nasce no Next (só o Better Auth gera token que ele aceita) e o
    WhatsApp sai daqui (só o backend tem `build_outbound_client`). Este corpo
    é a ponte entre os dois mundos.
    """

    link: str = Field(min_length=8, max_length=2000)
    expira_em: datetime


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@router.get("")
async def list_endpoint(
    search: str | None = None,
    perfil_id: int | None = None,
    departamento_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Lista usuários da empresa com filtros + paginação server-side."""
    pool = await get_pool()
    items, total = await list_usuarios_da_empresa(
        pool,
        empresa_id,
        search=search,
        perfil_id=perfil_id,
        departamento_id=departamento_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [u.to_dict() for u in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{user_id}")
async def get_endpoint(
    user_id: str,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("empresa.member.add")),
):
    pool = await get_pool()
    u = await get_usuario(pool, empresa_id, user_id)
    if u is None:
        raise HTTPException(
            status_code=404, detail="Usuário não encontrado nesta empresa."
        )
    return u.to_dict()


@router.get("/{user_id}/atividade")
async def atividade_endpoint(
    user_id: str,
    limit: int = 50,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Histórico de auditoria (`audit_governanca`) do usuário — quem
    criou/alterou/desativou. Read-only, enriquecido com o nome do ator."""
    pool = await get_pool()
    eventos = await list_audit_governanca(
        pool,
        empresa_id=empresa_id,
        target_user_id=user_id,
        limit=min(max(limit, 1), 200),
    )
    nomes = await resolve_user_names(pool, [e["actor_user_id"] for e in eventos])
    for e in eventos:
        e["actor_nome"] = nomes.get(e["actor_user_id"])
    return {"items": eventos}


@router.post("", status_code=201)
async def create_endpoint(
    body: CreateUsuarioInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("empresa.member.add")),
    # ADR-005 leva A: `limite_usuarios` era só contado no /billing.
    _quota: None = Depends(require_plano_limit("usuarios")),
):
    """Cria usuário + membership + perfis + deptos. Senha vem em chamada
    separada (Server Action chama Better Auth.setUserPassword).

    Retorna usuário enriquecido. Frontend faz fluxo:
    1. POST /api/usuarios → obtém user_id
    2. Server Action: auth.api.setUserPassword({userId, newPassword: gerada})
    3. Mostra senha UMA vez pro admin copiar
    """
    pool = await get_pool()
    telefone = _telefone_normalizado_ou_400(body.telefone)
    try:
        u = await criar_usuario_completo(
            pool,
            empresa_id=empresa_id,
            nome=body.nome,
            email=body.email,
            telefone=telefone,
            role_legacy=body.role_legacy,
            perfis_ids=body.perfis_ids,
            departamentos_ids=body.departamentos_ids,
            conexoes=(
                [c.model_dump() for c in body.conexoes]
                if body.conexoes is not None
                else None
            ),
            atendente_max_paralelos=body.atendente_max_paralelos,
            criado_por_user_id=user_id,
        )
    except TenantValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        msg = str(e).lower()
        if "duplicate key" in msg and "email" in msg:
            raise HTTPException(
                status_code=409,
                detail=f"Email '{body.email}' já cadastrado.",
            ) from e
        raise
    return u.to_dict()


@router.put("/{user_id}")
async def update_endpoint(
    user_id: str,
    body: UpdateUsuarioInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("empresa.member.add")),
):
    pool = await get_pool()
    telefone = _telefone_normalizado_ou_400(body.telefone)
    try:
        u = await atualizar_usuario(
            pool,
            empresa_id=empresa_id,
            user_id=user_id,
            nome=body.nome,
            email=body.email,
            telefone=telefone,
            role_legacy=body.role_legacy,
            perfis_ids=body.perfis_ids,
            departamentos_ids=body.departamentos_ids,
            conexoes=(
                [c.model_dump() for c in body.conexoes]
                if body.conexoes is not None
                else None
            ),
        )
    except TenantValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        msg = str(e).lower()
        if "duplicate key" in msg and "email" in msg:
            raise HTTPException(
                status_code=409,
                detail=f"Email '{body.email}' já cadastrado em outro usuário.",
            ) from e
        raise
    if u is None:
        raise HTTPException(
            status_code=404, detail="Usuário não encontrado nesta empresa."
        )
    return u.to_dict()


@router.post("/{user_id}/convite")
async def convite_endpoint(
    user_id: str,
    body: ConviteInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    actor_user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Envia o convite de acesso (link de definição de senha) no WhatsApp.

    Devolve **200 com `ok: false` e o motivo** quando o envio não sai — a
    falha é do WhatsApp (sem telefone, sem conexão, provedor recusou), não do
    request, e a tela precisa do texto para cair no plano B (mostrar a senha).

    O link chega no corpo, vai para o provedor, e MORRE aqui: não entra em
    log, nem na auditoria, nem na resposta.
    """
    from whatsapp_langchain.shared.convite_acesso import (
        ConviteError,
        enviar_convite,
    )

    pool = await get_pool()
    u = await get_usuario(pool, empresa_id=empresa_id, user_id=user_id)
    if u is None:
        raise HTTPException(
            status_code=404, detail="Usuário não encontrado nesta empresa."
        )

    parsed = urlparse(body.link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Link inválido.")
    painel_url = f"{parsed.scheme}://{parsed.netloc}"

    try:
        telefone = await enviar_convite(
            pool,
            empresa_id=empresa_id,
            user_id=user_id,
            link=body.link,
            expira_em=body.expira_em,
            painel_url=painel_url,
        )
    except ConviteError as e:
        logger.info(
            "convite_acesso_nao_enviado",
            user_id=user_id,
            empresa_id=empresa_id,
            motivo=str(e),
        )
        return {"ok": False, "erro": str(e)}

    await record_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        action="member.convite",
        entity_type="empresa_membro",
        entity_id=user_id,
        payload_after={"telefone": telefone},  # o número, NUNCA o link
        request=request,
    )
    return {"ok": True, "telefone": telefone}


@router.get("/exists/{user_id}")
async def exists_endpoint(
    user_id: str,
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Confirma se user existe (pra Server Action validar antes de reset).

    Sprint U.4 — não busca por email (que pode ser NULL). Busca por id.
    """
    pool = await get_pool()
    found = await verificar_user_existe(pool, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Usuário não existe.")
    return found


@router.post("/{user_id}/sessions/invalidate", status_code=204)
async def invalidate_sessions_endpoint(
    user_id: str,
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Apaga todas auth.session do user (força re-login).
    Chamado após Better Auth.setUserPassword pra invalidar tokens antigos."""
    pool = await get_pool()
    n = await invalidar_sessions(pool, user_id)
    logger.info("usuario_sessions_invalidated", user_id=user_id, count=n)


@router.post("/{user_id}/avatar")
async def upload_avatar_endpoint(
    user_id: str,
    file: UploadFile = File(...),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("empresa.member.add")),
):
    """Upload avatar — re-encoda pra PNG 256x256 via Pillow.

    Valida MIME + tamanho. Path local: /uploads/avatars/{user_id}.png
    """
    # Confirma user existe na empresa
    pool = await get_pool()
    u = await get_usuario(pool, empresa_id, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Lê + valida
    content = await file.read()
    max_mb = _AVATAR_MAX_BYTES // 1024 // 1024
    if len(content) > _AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {max_mb} MB.",
        )
    if file.content_type not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Use: PNG, JPEG, WebP ou GIF.",
        )

    # Re-encode via Pillow (defesa: nunca confia no MIME do client)
    try:
        from PIL import Image
    except ImportError as e:
        raise HTTPException(
            status_code=503, detail="Pillow não disponível no servidor."
        ) from e
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()  # checa que é imagem válida
        img = Image.open(io.BytesIO(content))  # re-abre após verify (consome)
        # Converte RGBA→RGB se necessário, redimensiona pra 256x256 (mantém aspect)
        img.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            # PNG suporta alpha; pra simplificar salva como PNG sempre
            pass
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Imagem inválida: {e}") from e

    safe_id = _avatar_safe_id(user_id)
    _AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _AVATARS_DIR / f"{safe_id}.png"
    img.save(out_path, format="PNG", optimize=True)

    rel_path = f"/uploads/avatars/{safe_id}.png"
    await set_avatar_path(pool, user_id, rel_path)

    logger.info(
        "usuario_avatar_uploaded",
        user_id=user_id,
        size_bytes=len(content),
        path=rel_path,
    )
    return {"avatar_path": rel_path}


@router.patch("/{user_id}/status")
async def set_status_endpoint(
    user_id: str,
    body: StatusUsuarioInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    actor_user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("empresa.member.status")),
):
    """Ativa/desabilita o usuário (nativo, sem endpoint legado).

    Ao desabilitar, opcionalmente transfere os atendimentos abertos do user
    (`on_disable`): `reassign` p/ outro atendente, `departamento` devolve à
    fila do depto, ou `none` (deixa como está). Retorna `{status, transferidos}`.
    """
    pool = await get_pool()

    role = await get_role_legacy(pool, empresa_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=404, detail="Usuário não é membro desta empresa."
        )
    if body.status == "disabled":
        if user_id == actor_user_id:
            raise HTTPException(
                status_code=400, detail="Você não pode desabilitar a si mesmo."
            )
        if role == "admin" and await contar_admins_empresa(pool, empresa_id) <= 1:
            raise HTTPException(
                status_code=409,
                detail="Não é possível desabilitar o último admin da empresa.",
            )

    transferidos = 0
    if body.status == "disabled" and body.on_disable != "none":
        abertos = await list_atendimentos(
            pool, empresa_id, tipo="meus", current_user_id=user_id, limit=500
        )
        for at in abertos:
            if body.on_disable == "reassign" and body.target_user_id:
                await transfer_atendimento(pool, at.id, body.target_user_id)
            elif body.on_disable == "departamento" and body.departamento_id:
                await transfer_atendimento_to_departamento(
                    pool, at.id, body.departamento_id
                )
            else:
                continue
            transferidos += 1

    ok = await set_user_status(pool, user_id, status=body.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    await record_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        action="member.disable" if body.status == "disabled" else "member.enable",
        entity_type="auth.user",
        entity_id=user_id,
        payload_after={"status": body.status, "transferidos": transferidos},
        request=request,
    )
    logger.info(
        "usuario_status_alterado",
        empresa_id=empresa_id,
        user_id=user_id,
        status=body.status,
        transferidos=transferidos,
    )
    return {"status": body.status, "transferidos": transferidos}


@router.post("/{user_id}/replicar", status_code=201)
async def replicar_endpoint(
    user_id: str,
    body: ReplicarUsuarioInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    actor_user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("empresa.member.add")),
    # Replicar também cria um usuário — mesmo limite do create.
    _quota: None = Depends(require_plano_limit("usuarios")),
):
    """Clona perfis+deptos+conexões+role+capacidade de um usuário existente
    pra um novo (paridade ZigChat `replicarUsuario`). Senha gerada no fluxo
    normal do create pela Server Action do frontend."""
    pool = await get_pool()
    telefone = _telefone_normalizado_ou_400(body.telefone)
    try:
        u = await replicar_usuario(
            pool,
            empresa_id=empresa_id,
            origem_user_id=user_id,
            nome=body.nome,
            email=body.email,
            telefone=telefone,
            criado_por_user_id=actor_user_id,
        )
    except TenantValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        msg = str(e).lower()
        if "duplicate key" in msg and "email" in msg:
            raise HTTPException(
                status_code=409, detail=f"Email '{body.email}' já cadastrado."
            ) from e
        raise
    await record_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=actor_user_id,
        target_user_id=u.id,
        action="member.add",
        entity_type="empresa_membro",
        entity_id=u.id,
        payload_after={"replicado_de": user_id},
        request=request,
    )
    return u.to_dict()


@router.delete("/{user_id}", status_code=204)
async def delete_endpoint(
    user_id: str,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    actor_user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("empresa.member.remove")),
):
    """Remove o vínculo do usuário com a empresa (+ perfis/deptos/conexões +
    avatar). Se era a última empresa do user, desabilita o auth.user."""
    pool = await get_pool()
    if user_id == actor_user_id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo.")
    role = await get_role_legacy(pool, empresa_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=404, detail="Usuário não é membro desta empresa."
        )
    if role == "admin" and await contar_admins_empresa(pool, empresa_id) <= 1:
        raise HTTPException(
            status_code=409,
            detail="Não é possível remover o último admin da empresa.",
        )

    result = await remover_usuario_da_empresa(pool, empresa_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if result.get("avatar_path"):
        _delete_avatar_file(user_id)

    await record_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        action="member.remove",
        entity_type="empresa_membro",
        entity_id=user_id,
        payload_after={"auth_disabled": result.get("auth_disabled", False)},
        request=request,
    )
