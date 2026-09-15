"""Endpoints de gestão de empresas e membros (M1.x).

Mutações exigem que o user seja admin da empresa-alvo ou superadmin
global. Cada endpoint valida explicitamente — não usamos role-guard
genérico pra manter as regras (ex: "remover último admin" → 409) no
lugar onde a operação acontece.
"""

import base64
import io
import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_plano import assert_plano_feature
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import (
    add_member,
    create_empresa,
    get_empresa_by_id,
    get_user_status,
    is_admin_of,
    is_superadmin,
    list_members,
    remove_member,
    set_onboarding_dispensado,
    set_user_status,
    update_empresa,
    update_empresa_csat,
    update_member_role,
)
from whatsapp_langchain.shared.models import Empresa, EmpresaMembro
from whatsapp_langchain.shared.voz import VOZES, VozError, sintetizar

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/empresas",
    tags=["empresa_admin"],
    dependencies=[Depends(verify_service_token)],
)


_SLUG_PATTERN = r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$"


class CreateEmpresaInput(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=_SLUG_PATTERN)
    plano: str = "free"
    doc: str | None = None
    # Fiscal (opcional na criação — UI pede só básico)
    razao_social: str | None = None
    inscricao_estadual: str | None = None
    endereco_fiscal_cep: str | None = None
    endereco_fiscal_logradouro: str | None = None
    endereco_fiscal_numero: str | None = None
    endereco_fiscal_complemento: str | None = None
    endereco_fiscal_bairro: str | None = None
    endereco_fiscal_cidade: str | None = None
    endereco_fiscal_uf: str | None = Field(default=None, max_length=2)


class UpdateEmpresaInput(BaseModel):
    nome: str | None = None
    slug: str | None = Field(default=None, pattern=_SLUG_PATTERN)
    plano: str | None = None
    doc: str | None = None
    status: str | None = None
    razao_social: str | None = None
    inscricao_estadual: str | None = None
    endereco_fiscal_cep: str | None = None
    endereco_fiscal_logradouro: str | None = None
    endereco_fiscal_numero: str | None = None
    endereco_fiscal_complemento: str | None = None
    endereco_fiscal_bairro: str | None = None
    endereco_fiscal_cidade: str | None = None
    endereco_fiscal_uf: str | None = Field(default=None, max_length=2)
    # White-label (mig 115)
    nome_exibicao: str | None = Field(default=None, max_length=80)
    cor_primaria: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    cor_secundaria: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    # Voz do agente (mig 176) — patch parcial: None = não mexe. voz_estilo=""
    # limpa o estilo (a coluna é NOT NULL DEFAULT '').
    voz_ativa: bool | None = None
    voz_nome: str | None = None
    voz_estilo: str | None = Field(default=None, max_length=200)
    # Retenção (mig 185): dias; 0 = ilimitado. None = não mexe (patch parcial).
    retencao_dias: int | None = Field(default=None, ge=0, le=3650)


class AddMemberInput(BaseModel):
    user_id: str = Field(min_length=1)
    role: str = "operator"


class UpdateRoleInput(BaseModel):
    role: str


VALID_ROLES = {"admin", "operator", "viewer"}

# Detail pt-BR do 402 quando o plano não tem a feature 'voz' (mig 177).
# A UI mostra `detail.message` direto (lib/api-error-shared) — sem jargão.
_VOZ_PLANO_MSG = "Resposta em áudio está disponível nos planos Pro e Enterprise."


def _check_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválido. Valores aceitos: {sorted(VALID_ROLES)}.",
        )


@router.post("", response_model=Empresa)
async def create_empresa_endpoint(
    body: CreateEmpresaInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Cria empresa. Quem cria vira admin. Slug único globalmente."""
    pool = await get_pool()
    try:
        empresa = await create_empresa(
            pool,
            body.nome,
            body.slug,
            body.plano,
            body.doc,
            user_id,
            razao_social=body.razao_social,
            inscricao_estadual=body.inscricao_estadual,
            endereco_fiscal_cep=body.endereco_fiscal_cep,
            endereco_fiscal_logradouro=body.endereco_fiscal_logradouro,
            endereco_fiscal_numero=body.endereco_fiscal_numero,
            endereco_fiscal_complemento=body.endereco_fiscal_complemento,
            endereco_fiscal_bairro=body.endereco_fiscal_bairro,
            endereco_fiscal_cidade=body.endereco_fiscal_cidade,
            endereco_fiscal_uf=body.endereco_fiscal_uf,
        )
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Slug já em uso.") from e
        raise
    logger.info("empresa_created", empresa_id=empresa.id, criador=user_id)
    return empresa


@router.put("/{empresa_id}", response_model=Empresa)
async def update_empresa_endpoint(
    empresa_id: int,
    body: UpdateEmpresaInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza campos da empresa. Só admin local ou superadmin.

    Guard: se body.slug == slug atual da empresa, NÃO inclui no UPDATE
    (evita UniqueViolation falso quando user só queria mudar status).
    Captura UniqueViolation no slug e retorna 409 com mensagem clara.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")

    if body.voz_nome is not None and body.voz_nome not in VOZES:
        raise HTTPException(
            status_code=400,
            detail=f"Voz inválida. Valores aceitos: {sorted(VOZES)}.",
        )

    # Feature de plano (mig 177): LIGAR a voz exige plano com 'voz'.
    # Desligar (False) ou mexer só em voz_nome/voz_estilo continua livre —
    # a config fica guardada pra quando o plano voltar a ter a feature.
    if body.voz_ativa is True:
        await assert_plano_feature(empresa_id, "voz", mensagem=_VOZ_PLANO_MSG)

    # Se slug enviado == slug atual, skipa pra não disparar UNIQUE check.
    if body.slug:
        from whatsapp_langchain.shared.empresa import get_empresa_by_id

        current = await get_empresa_by_id(pool, empresa_id)
        if current and current.slug == body.slug:
            body.slug = None

    try:
        out = await update_empresa(
            pool,
            empresa_id,
            nome=body.nome,
            slug=body.slug,
            plano=body.plano,
            doc=body.doc,
            status=body.status,
            razao_social=body.razao_social,
            inscricao_estadual=body.inscricao_estadual,
            endereco_fiscal_cep=body.endereco_fiscal_cep,
            endereco_fiscal_logradouro=body.endereco_fiscal_logradouro,
            endereco_fiscal_numero=body.endereco_fiscal_numero,
            endereco_fiscal_complemento=body.endereco_fiscal_complemento,
            endereco_fiscal_bairro=body.endereco_fiscal_bairro,
            endereco_fiscal_cidade=body.endereco_fiscal_cidade,
            endereco_fiscal_uf=body.endereco_fiscal_uf,
            nome_exibicao=body.nome_exibicao,
            cor_primaria=body.cor_primaria,
            cor_secundaria=body.cor_secundaria,
            voz_ativa=body.voz_ativa,
            voz_nome=body.voz_nome,
            voz_estilo=body.voz_estilo,
            retencao_dias=body.retencao_dias,
        )
    except Exception as e:
        msg = str(e).lower()
        if "empresa_slug_key" in msg or ("duplicate key" in msg and "slug" in msg):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Slug '{body.slug}' já está em uso por outra empresa. "
                    "Escolha outro identificador."
                ),
            ) from e
        raise
    if out is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return out


# --- Voz do agente: preview (mig 176) ---

# Frase fixa e curta de propósito: preview é pra escolher a voz, não pra
# testar texto — e cada chamada custa TTS de verdade (registrado no budget).
_VOZ_PREVIEW_FRASE = "Olá! Esta é uma amostra da voz do atendimento."


class VozPreviewInput(BaseModel):
    voz_nome: str = "alloy"
    voz_estilo: str = Field(default="", max_length=200)


@router.post("/{empresa_id}/voz/preview")
async def preview_voz_endpoint(
    empresa_id: int,
    body: VozPreviewInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Sintetiza uma amostra curta da voz escolhida (sem persistir nada).

    Mesmo gate dos vizinhos do arquivo: service token (router) + admin da
    empresa. O custo entra em ia_execucao/ia_budget da própria empresa —
    preview não é de graça.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode testar a voz.")
    # Feature de plano (mig 177): preview também é TTS pago — mesmo gate
    # do PUT. Empresa vem do PATH, por isso o helper e não o Depends do
    # require_plano_feature (que resolve pelo header X-Empresa-Id).
    await assert_plano_feature(empresa_id, "voz", mensagem=_VOZ_PLANO_MSG)
    if body.voz_nome not in VOZES:
        raise HTTPException(
            status_code=400,
            detail=f"Voz inválida. Valores aceitos: {sorted(VOZES)}.",
        )
    try:
        ogg = await sintetizar(
            _VOZ_PREVIEW_FRASE,
            voz=body.voz_nome,
            estilo=body.voz_estilo,
            pool=pool,
            empresa_id=empresa_id,
        )
    except VozError as e:
        logger.warning("voz_preview_falhou", empresa_id=empresa_id, error=str(e))
        raise HTTPException(
            status_code=502,
            detail="Não foi possível gerar a amostra de voz agora. Tente de novo.",
        ) from e
    return {
        "audio_base64": base64.b64encode(ogg).decode("ascii"),
        "mime": "audio/ogg",
    }


# --- White-label: upload de logo (mig 115) ---

_LOGOS_DIR = Path(os.environ.get("LOGOS_DIR", "/app/uploads/logos"))
_LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_LOGO_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@router.post("/{empresa_id}/logo")
async def upload_logo_endpoint(
    empresa_id: int,
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id_from_request),
):
    """Sobe a logo da empresa (white-label). Só admin/superadmin.

    Re-encoda via Pillow pra PNG (≤512px, preserva alpha). Path local
    `/uploads/logos/{empresa_id}.png` servido como estático.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")

    content = await file.read()
    max_mb = _LOGO_MAX_BYTES // 1024 // 1024
    if len(content) > _LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail=f"Arquivo muito grande. Máximo: {max_mb} MB."
        )
    if file.content_type not in _LOGO_ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Use: PNG, JPEG, WebP ou GIF.",
        )

    try:
        from PIL import Image
    except ImportError as e:
        raise HTTPException(
            status_code=503, detail="Pillow não disponível no servidor."
        ) from e
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))  # re-abre após verify
        # Mantém aspecto + alpha (PNG). 512px serve pra retina no sidebar.
        img.thumbnail((512, 512), Image.Resampling.LANCZOS)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Imagem inválida: {e}") from e

    _LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _LOGOS_DIR / f"{empresa_id}.png"
    img.save(out_path, format="PNG", optimize=True)

    rel_path = f"/uploads/logos/{empresa_id}.png"
    updated = await update_empresa(pool, empresa_id, logo_path=rel_path)
    if updated is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    logger.info(
        "empresa_logo_uploaded",
        empresa_id=empresa_id,
        size_bytes=len(content),
        path=rel_path,
    )
    return {"logo_path": rel_path}


# Sprint Y: configuração da pesquisa NPS por empresa
class CsatConfig(BaseModel):
    csat_ativo: bool
    csat_pergunta: str | None = None
    csat_msg_agradecimento: str | None = None
    csat_solicita_comentario: bool = True


class ResumoDiarioConfig(BaseModel):
    resumo_diario_ativo: bool
    resumo_diario_telefone: str | None = Field(default=None, max_length=32)
    resumo_diario_horario: str = Field(default="22:30", pattern=r"^\d{2}:\d{2}$")
    resumo_diario_dias: list[int] = Field(default=[1, 2, 3, 4, 5])
    resumo_diario_tz: str = Field(default="America/Campo_Grande", max_length=64)

    # Somente leitura (mig 162) — o PUT aceita e ignora. Existem porque, sem
    # eles, "não chegou nada" e "falhou às 17:00 por X" eram o mesmo silêncio
    # na tela: o único registro do envio era log de worker, que some no deploy.
    ultimo_status: str | None = None
    ultimo_erro: str | None = None
    ultima_tentativa_em: str | None = None


@router.get("/{empresa_id}/resumo-diario", response_model=ResumoDiarioConfig)
async def get_resumo_diario_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Config do resumo diário por WhatsApp (mig 135). Membro lê."""
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT resumo_diario_ativo, resumo_diario_telefone,
                      resumo_diario_horario, resumo_diario_dias,
                      resumo_diario_tz, resumo_diario_last_status,
                      resumo_diario_last_error, resumo_diario_last_attempt_at
                 FROM empresa WHERE id = %s""",
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return ResumoDiarioConfig(
        resumo_diario_ativo=bool(row[0]),
        resumo_diario_telefone=row[1],
        resumo_diario_horario=row[2].strftime("%H:%M") if row[2] else "22:30",
        resumo_diario_dias=list(row[3] or [1, 2, 3, 4, 5]),
        resumo_diario_tz=row[4] or "America/Campo_Grande",
        ultimo_status=row[5],
        ultimo_erro=row[6],
        ultima_tentativa_em=row[7].isoformat() if row[7] else None,
    )


@router.put("/{empresa_id}/resumo-diario", response_model=ResumoDiarioConfig)
async def update_resumo_diario_endpoint(
    empresa_id: int,
    body: ResumoDiarioConfig,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza config do resumo diário. Só admin local ou superadmin."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")
    if body.resumo_diario_ativo and not (body.resumo_diario_telefone or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Informe o telefone de destino pra ativar o resumo.",
        )
    dias = sorted({d for d in body.resumo_diario_dias if 1 <= d <= 7})
    if body.resumo_diario_ativo and not dias:
        raise HTTPException(
            status_code=400, detail="Selecione pelo menos um dia da semana."
        )
    from whatsapp_langchain.shared.campanha import normalize_phone

    telefone = (
        normalize_phone(body.resumo_diario_telefone)
        if body.resumo_diario_telefone
        else None
    )
    if body.resumo_diario_ativo and not telefone:
        raise HTTPException(status_code=400, detail="Telefone inválido.")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """UPDATE empresa SET
                   resumo_diario_ativo = %s,
                   resumo_diario_telefone = %s,
                   resumo_diario_horario = %s::time,
                   resumo_diario_dias = %s,
                   resumo_diario_tz = %s,
                   updated_at = NOW()
                 WHERE id = %s""",
            (
                body.resumo_diario_ativo,
                telefone,
                body.resumo_diario_horario,
                dias or [1, 2, 3, 4, 5],
                body.resumo_diario_tz,
                empresa_id,
            ),
        )
        await conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return ResumoDiarioConfig(
        resumo_diario_ativo=body.resumo_diario_ativo,
        resumo_diario_telefone=telefone,
        resumo_diario_horario=body.resumo_diario_horario,
        resumo_diario_dias=dias or [1, 2, 3, 4, 5],
        resumo_diario_tz=body.resumo_diario_tz,
    )


@router.post("/{empresa_id}/resumo-diario/testar")
async def testar_resumo_diario_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Envia o resumo AGORA, pra validar a configuração.

    Sem isto, conferir se o resumo funciona custa um dia por tentativa: o
    agendamento tem uma chance por dia local, e trocar o horário não devolve
    essa chance. O envio manual não consome o dia do agendamento.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode testar.")

    from whatsapp_langchain.shared.resumo_diario import enviar_resumo_agora

    ok, erro = await enviar_resumo_agora(pool, empresa_id)
    if not ok:
        # 200 com ok=false: a falha do provedor é o RESULTADO do teste, não um
        # erro da requisição — a tela mostra o motivo em vez de "algo deu errado".
        return {"ok": False, "erro": erro}
    return {"ok": True, "erro": None}


@router.get("/{empresa_id}/csat", response_model=CsatConfig)
async def get_empresa_csat_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Lê a config CSAT da empresa. Acesso pra qualquer membro (admin lê
    + pode editar; não-admin só vê)."""
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT csat_ativo, csat_pergunta, csat_msg_agradecimento,
                      csat_solicita_comentario FROM empresa WHERE id = %s""",
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return CsatConfig(
        csat_ativo=bool(row[0]),
        csat_pergunta=row[1],
        csat_msg_agradecimento=row[2],
        csat_solicita_comentario=bool(row[3]),
    )


@router.put("/{empresa_id}/csat", response_model=CsatConfig)
async def update_empresa_csat_endpoint(
    empresa_id: int,
    body: CsatConfig,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza config CSAT da empresa. Só admin local ou superadmin."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")
    ok = await update_empresa_csat(
        pool,
        empresa_id,
        csat_ativo=body.csat_ativo,
        csat_pergunta=body.csat_pergunta,
        csat_msg_agradecimento=body.csat_msg_agradecimento,
        csat_solicita_comentario=body.csat_solicita_comentario,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    logger.info(
        "empresa_csat_updated",
        empresa_id=empresa_id,
        csat_ativo=body.csat_ativo,
        actor=user_id,
    )
    return body


class OnboardingDispensaInput(BaseModel):
    dispensado: bool = True


class OnboardingStatus(BaseModel):
    empresa_id: int
    empresa_nome: str
    empresa_doc_ok: bool
    conexoes_count: int
    agentes_count: int
    atendentes_count: int
    completo: bool
    dispensado: bool


@router.get("/{empresa_id}/onboarding", response_model=OnboardingStatus)
async def get_onboarding_status_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Os 4 checks do wizard, numa query só.

    Antes o frontend montava isso chamando 4 endpoints e contando o que vinha.
    Duas fragilidades, ambas com o mesmo sintoma — o wizard reaparecendo em
    todo login:

    1. **Formato.** `/empresas/{id}/membros` devolve lista pura, mas o front
       lia `.items` dela. `undefined?.length ?? 0` = 0 sem erro nenhum, então
       o passo 4 ficava eternamente pendente com 10 atendentes cadastrados.
    2. **Permissão.** `/v1/agentes` exige `agente.config`. Operador sem essa
       permissão tomava 403, o `.catch` virava lista vazia, e o passo 3 nunca
       completava — pra ele o onboarding era um beco sem saída.

    O estado do onboarding é da **empresa**, não de quem pergunta. Por isso
    aqui basta ser membro: a resposta é a mesma para todo mundo da empresa.
    """
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT e.nome,
                   e.doc IS NOT NULL AND e.doc <> '' AS doc_ok,
                   e.onboarding_dispensado_at IS NOT NULL AS dispensado,
                   (SELECT count(*) FROM conexao c WHERE c.empresa_id = e.id),
                   (SELECT count(*) FROM agente_ia a WHERE a.empresa_id = e.id),
                   (SELECT count(*) FROM empresa_membro m WHERE m.empresa_id = e.id)
              FROM empresa e
             WHERE e.id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    nome, doc_ok, dispensado, conexoes, agentes, atendentes = row
    return OnboardingStatus(
        empresa_id=empresa_id,
        empresa_nome=nome,
        empresa_doc_ok=bool(doc_ok),
        conexoes_count=int(conexoes),
        agentes_count=int(agentes),
        atendentes_count=int(atendentes),
        completo=bool(doc_ok) and conexoes > 0 and agentes > 0 and atendentes > 0,
        dispensado=bool(dispensado),
    )


@router.put("/{empresa_id}/onboarding-dispensado", response_model=Empresa)
async def set_onboarding_dispensado_endpoint(
    empresa_id: int,
    body: OnboardingDispensaInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Lembra que o wizard de onboarding foi dispensado (mig 160).

    Qualquer membro pode dispensar — quem está vendo a tela é quem quer sair
    dela, e exigir admin faria o botão "Pular" falhar calado justo pro
    operador, que é quem mais topa com o wizard. Escrever é inofensivo:
    mexe só em qual tela a raiz "/" abre.
    """
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    empresa = await set_onboarding_dispensado(
        pool, empresa_id, dispensado=body.dispensado
    )
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    logger.info(
        "empresa_onboarding_dispensado",
        empresa_id=empresa_id,
        dispensado=body.dispensado,
        actor=user_id,
    )
    return empresa


@router.get("/{empresa_id}/membros", response_model=list[EmpresaMembro])
async def list_members_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Lista membros — qualquer membro da empresa (ou superadmin) pode ver."""
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        m = await get_empresa_membership(pool, empresa_id, user_id)
        if m is None:
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    if await get_empresa_by_id(pool, empresa_id) is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return await list_members(pool, empresa_id)


@router.post("/{empresa_id}/membros", response_model=EmpresaMembro)
async def add_member_endpoint(
    empresa_id: int,
    body: AddMemberInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Adiciona membro. Só admin local ou superadmin."""
    _check_role(body.role)
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode adicionar membros.")
    if await get_empresa_by_id(pool, empresa_id) is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return await add_member(pool, empresa_id, body.user_id, body.role)


@router.put("/{empresa_id}/membros/{member_user_id}", response_model=EmpresaMembro)
async def update_member_role_endpoint(
    empresa_id: int,
    member_user_id: str,
    body: UpdateRoleInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza role. Bloqueia demote do último admin (409)."""
    _check_role(body.role)
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode mudar roles.")
    out = await update_member_role(pool, empresa_id, member_user_id, body.role)
    if out is None:
        raise HTTPException(
            status_code=409,
            detail="Não é possível demote do último admin da empresa.",
        )
    return out


@router.delete("/{empresa_id}/membros/{member_user_id}", status_code=204)
async def remove_member_endpoint(
    empresa_id: int,
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
):
    """Remove membro. Bloqueia remoção do último admin (409)."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode remover membros.")
    ok = await remove_member(pool, empresa_id, member_user_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Membro não existe ou seria o último admin (não removível).",
        )


# ---------------------------------------------------------------------------
# Status do user — ativar/desativar (E1.7)
# ---------------------------------------------------------------------------


class UpdateStatusInput(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


@router.put("/{empresa_id}/membros/{member_user_id}/status")
async def update_member_status(
    empresa_id: int,
    member_user_id: str,
    body: UpdateStatusInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Ativa/desativa user (auth.user.status).

    Desativar: remove sessões ativas + bloqueia novos logins até reativar.
    Ativar: libera login (sessões antigas continuam expiradas — user
    precisa logar de novo).

    Proteções:
    - Só admin da empresa OU superadmin pode mudar status
    - Não permite desativar a si mesmo (evita lockout acidental)
    - Não permite desativar o último admin da empresa (proteção paralela
      ao update_member_role)
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode mudar status.")

    if member_user_id == user_id and body.status == "disabled":
        raise HTTPException(
            status_code=409,
            detail="Você não pode desativar a si mesmo. Peça para outro admin.",
        )

    # Quando desativando, validar que não é o último admin da empresa
    if body.status == "disabled":
        members = await list_members(pool, empresa_id)
        admins_ativos = [
            m for m in members if m.role == "admin" and m.user_id != member_user_id
        ]
        target_member = next((m for m in members if m.user_id == member_user_id), None)
        if target_member and target_member.role == "admin" and not admins_ativos:
            raise HTTPException(
                status_code=409,
                detail="Não pode desativar o último admin da empresa.",
            )

    affected = await set_user_status(pool, member_user_id, status=body.status)
    if not affected:
        raise HTTPException(status_code=404, detail="User não encontrado.")

    logger.info(
        "user_status_changed",
        target_user_id=member_user_id,
        new_status=body.status,
        actor_user_id=user_id,
        empresa_id=empresa_id,
    )
    return {"user_id": member_user_id, "status": body.status}


@router.get("/users/{member_user_id}/status")
async def get_status(
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lê status do user. Acessível por superadmin OU pelo próprio user."""
    pool = await get_pool()
    if member_user_id != user_id and not await is_superadmin(pool, user_id):
        raise HTTPException(
            status_code=403,
            detail="Só superadmin ou o próprio user pode ver status.",
        )
    status = await get_user_status(pool, member_user_id)
    if status is None:
        raise HTTPException(status_code=404, detail="User não encontrado.")
    return {"user_id": member_user_id, "status": status}


# ---------------------------------------------------------------------------
# Atribuição perfil <-> user e departamento <-> user (Sprint Governança RBAC)
# ---------------------------------------------------------------------------


class SyncPerfisInput(BaseModel):
    perfil_ids: list[int] = Field(default_factory=list, max_length=20)


class SyncDepartamentosInput(BaseModel):
    departamento_ids: list[int] = Field(default_factory=list, max_length=50)


async def _list_user_perfil_ids(pool, empresa_id: int, user_id: str) -> list[int]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT up.perfil_id
              FROM usuario_perfil up
              JOIN perfil_acesso pa ON pa.id = up.perfil_id
             WHERE up.user_id = %s AND pa.empresa_id = %s
             ORDER BY pa.nome
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def _list_user_departamento_ids(pool, empresa_id: int, user_id: str) -> list[int]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT ud.departamento_id
              FROM usuario_departamento ud
              JOIN departamento d ON d.id = ud.departamento_id
             WHERE ud.user_id = %s AND d.empresa_id = %s
             ORDER BY d.nome
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


@router.get("/{empresa_id}/membros/{member_user_id}/perfis")
async def get_member_perfis(
    empresa_id: int,
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lista perfis (RBAC) atribuídos ao member na empresa."""
    pool = await get_pool()
    from whatsapp_langchain.shared.empresa import get_empresa_membership

    if not await get_empresa_membership(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    ids = await _list_user_perfil_ids(pool, empresa_id, member_user_id)
    return {"user_id": member_user_id, "perfil_ids": ids}


@router.put("/{empresa_id}/membros/{member_user_id}/perfis")
async def sync_member_perfis(
    request: Request,
    empresa_id: int,
    member_user_id: str,
    body: SyncPerfisInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Substitui o set de perfis do member (UPSERT sync).

    Audit em audit_governanca pra rastreabilidade LGPD.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403, detail="Só admin pode mudar perfis de membros."
        )

    before_ids = await _list_user_perfil_ids(pool, empresa_id, member_user_id)

    desired = set(body.perfil_ids)
    # Valida que perfis pertencem à empresa
    if desired:
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND id = ANY(%s)",
                (empresa_id, list(desired)),
            )
            valid = {r[0] for r in await cur.fetchall()}
        if valid != desired:
            invalid = desired - valid
            raise HTTPException(
                status_code=400,
                detail=f"Perfis inválidos pra esta empresa: {sorted(invalid)}",
            )

    current = set(before_ids)
    to_add = desired - current
    to_remove = current - desired

    async with pool.connection() as conn:
        if to_remove:
            await conn.execute(
                "DELETE FROM usuario_perfil WHERE user_id = %s "
                "AND empresa_id = %s AND perfil_id = ANY(%s)",
                (member_user_id, empresa_id, list(to_remove)),
            )
        for pid in to_add:
            await conn.execute(
                "INSERT INTO usuario_perfil "
                "(user_id, perfil_id, empresa_id, assigned_by_user_id) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (member_user_id, pid, empresa_id, user_id),
            )
        await conn.commit()

    after_ids = sorted(desired)

    # Audit best-effort
    try:
        from whatsapp_langchain.shared.audit_governanca import (
            record_audit_governanca,
        )

        await record_audit_governanca(
            pool,
            empresa_id=empresa_id,
            actor_user_id=user_id,
            target_user_id=member_user_id,
            action="perfil.sync",
            entity_type="usuario_perfil",
            entity_id=member_user_id,
            payload_before={"perfil_ids": sorted(before_ids)},
            payload_after={"perfil_ids": after_ids},
            request=request,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_perfil_sync_failed", error=str(exc))

    return {"user_id": member_user_id, "perfil_ids": after_ids}


@router.get("/{empresa_id}/membros/{member_user_id}/departamentos")
async def get_member_departamentos(
    empresa_id: int,
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lista departamentos vinculados ao member na empresa."""
    pool = await get_pool()
    from whatsapp_langchain.shared.empresa import get_empresa_membership

    if not await get_empresa_membership(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    ids = await _list_user_departamento_ids(pool, empresa_id, member_user_id)
    return {"user_id": member_user_id, "departamento_ids": ids}


@router.put("/{empresa_id}/membros/{member_user_id}/departamentos")
async def sync_member_departamentos(
    request: Request,
    empresa_id: int,
    member_user_id: str,
    body: SyncDepartamentosInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Substitui os departamentos vinculados ao member (UPSERT sync)."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403, detail="Só admin pode mudar deptos de membros."
        )

    before_ids = await _list_user_departamento_ids(pool, empresa_id, member_user_id)

    desired = set(body.departamento_ids)
    if desired:
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id FROM departamento WHERE empresa_id = %s AND id = ANY(%s)",
                (empresa_id, list(desired)),
            )
            valid = {r[0] for r in await cur.fetchall()}
        if valid != desired:
            invalid = desired - valid
            raise HTTPException(
                status_code=400,
                detail=(f"Departamentos inválidos pra esta empresa: {sorted(invalid)}"),
            )

    current = set(before_ids)
    to_add = desired - current
    to_remove = current - desired

    async with pool.connection() as conn:
        if to_remove:
            await conn.execute(
                "DELETE FROM usuario_departamento WHERE user_id = %s "
                "AND empresa_id = %s AND departamento_id = ANY(%s)",
                (member_user_id, empresa_id, list(to_remove)),
            )
        for did in to_add:
            await conn.execute(
                "INSERT INTO usuario_departamento "
                "(user_id, departamento_id, empresa_id) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (member_user_id, did, empresa_id),
            )
        await conn.commit()

    after_ids = sorted(desired)

    try:
        from whatsapp_langchain.shared.audit_governanca import (
            record_audit_governanca,
        )

        await record_audit_governanca(
            pool,
            empresa_id=empresa_id,
            actor_user_id=user_id,
            target_user_id=member_user_id,
            action="depto.sync",
            entity_type="usuario_departamento",
            entity_id=member_user_id,
            payload_before={"departamento_ids": sorted(before_ids)},
            payload_after={"departamento_ids": after_ids},
            request=request,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_depto_sync_failed", error=str(exc))

    return {"user_id": member_user_id, "departamento_ids": after_ids}


# ---------------------------------------------------------------------------
# Audit governança — viewer
# ---------------------------------------------------------------------------


@router.get("/{empresa_id}/audit/governanca")
async def list_audit_governanca_endpoint(
    empresa_id: int,
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lista eventos de audit_governanca com filtros opcionais."""
    pool = await get_pool()
    from whatsapp_langchain.shared.audit_governanca import (
        list_audit_governanca,
    )
    from whatsapp_langchain.shared.empresa import get_empresa_membership

    if not await get_empresa_membership(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")

    items = await list_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action=action,
        limit=min(max(limit, 1), 200),
        offset=max(offset, 0),
    )
    return {"items": items}


# Sprint Q.4 — endpoint quota (uso/limites/features do plano)
@router.get("/{empresa_id}/quota")
async def get_quota_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Retorna snapshot quota da empresa: plano + limites + uso + percentual.

    Usado por dashboard pra mostrar barra de progresso + upgrade prompt.
    Qualquer membro da empresa pode ler (não é dado sensível).
    """
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")

    from whatsapp_langchain.shared.plano_limits import get_quota_snapshot

    snap = await get_quota_snapshot(pool, empresa_id)
    return snap.to_dict()
