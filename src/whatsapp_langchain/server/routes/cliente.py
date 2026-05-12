"""CRUD de Clientes do painel admin (M3 CRM Light).

Endpoints escopados pela empresa ativa via `get_empresa_context`.
Mutações ficam abertas a qualquer membro no MVP — diferenciar por role
fica pra um milestone futuro.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.audit import diff_dicts, record_audit
from whatsapp_langchain.shared.cliente import (
    add_anotacao,
    add_tag,
    get_cliente_by_id,
    list_anotacoes,
    list_clientes,
    remove_tag,
    update_cliente_partial,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao
from whatsapp_langchain.shared.validators_br import (
    is_valid_cep,
    is_valid_cnpj,
    is_valid_cpf,
    is_valid_uf,
    normalize_cep,
    normalize_cnpj,
    normalize_cpf,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/clientes",
    tags=["clientes"],
    dependencies=[Depends(verify_service_token)],
)


class AnotacaoInput(BaseModel):
    conteudo: str = Field(min_length=1, max_length=4000)


class TagInput(BaseModel):
    tag: str = Field(min_length=1, max_length=64)


class ClienteDetail(BaseModel):
    """Resposta do GET /{id} — cliente + anotações cronológicas."""

    cliente: Cliente
    anotacoes: list[ClienteAnotacao]


@router.get("")
async def list_my_clientes(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Cliente]]:
    """Lista clientes da empresa ativa (mais recente primeiro)."""
    pool = await get_pool()
    rows = await list_clientes(
        pool, empresa_id, search=search, limit=limit, offset=offset
    )
    return {"clientes": rows}


async def _load_cliente_in_empresa(cliente_id: int, empresa_id: int) -> Cliente:
    """Helper: carrega + valida que o cliente pertence à empresa ativa."""
    pool = await get_pool()
    cliente = await get_cliente_by_id(pool, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    if cliente.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Cliente fora da empresa ativa.")
    return cliente


@router.get("/{cliente_id}")
async def read_cliente(
    cliente_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> ClienteDetail:
    """Detalhe de um cliente — inclui tags (no objeto) e anotações."""
    cliente = await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    anotacoes = await list_anotacoes(pool, cliente_id)
    return ClienteDetail(cliente=cliente, anotacoes=anotacoes)


class ClienteUpdateInput(BaseModel):
    """Update parcial do cliente (Fase 1.A — ficha enriquecida).

    Todos opcionais: send only what changes. Validators normalizam
    CPF/CNPJ/CEP (strip de máscara) e UF (uppercase).
    """

    nome: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)

    tipo_pessoa: str | None = Field(default=None, pattern=r"^(PF|PJ)?$")
    cpf: str | None = None
    cnpj: str | None = None
    rg: str | None = Field(default=None, max_length=30)
    razao_social: str | None = Field(default=None, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    data_nascimento: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    genero: str | None = Field(default=None, max_length=30)

    cep: str | None = None
    logradouro: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    complemento: str | None = Field(default=None, max_length=200)
    bairro: str | None = Field(default=None, max_length=120)
    cidade: str | None = Field(default=None, max_length=120)
    uf: str | None = None
    pais: str | None = Field(default=None, max_length=2)

    segmento: str | None = Field(default=None, max_length=120)
    lifecycle_stage: str | None = Field(
        default=None,
        pattern=r"^(lead|qualified|opportunity|customer|evangelist|churned)?$",
    )
    score: int | None = Field(default=None, ge=0, le=100)
    source: str | None = Field(default=None, max_length=120)
    responsavel_user_id: str | None = None
    valor_estimado_brl: float | None = Field(default=None, ge=0)

    instagram: str | None = Field(default=None, max_length=200)
    linkedin: str | None = Field(default=None, max_length=200)
    facebook: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    email_alternativo: str | None = Field(default=None, max_length=200)
    telefone_alternativo: str | None = Field(default=None, max_length=30)

    locale: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=60)
    avatar_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)

    # Sub-fase B+ (padrão profissional) (mig 046)
    whatsapp_state: str | None = Field(default=None, max_length=60)
    numero_verificado: bool | None = None
    whatsapp_lid: str | None = Field(default=None, max_length=200)
    remote_id: str | None = Field(default=None, max_length=200)
    msg_apos_encerramento: str | None = Field(default=None, max_length=2000)
    field_1: str | None = Field(default=None, max_length=500)
    field_2: str | None = Field(default=None, max_length=500)
    field_3: str | None = Field(default=None, max_length=500)
    field_4: str | None = Field(default=None, max_length=500)
    field_5: str | None = Field(default=None, max_length=500)
    ignora_inatividade: bool | None = None
    desconsidera_turno: bool | None = None


@router.put("/{cliente_id}")
async def update_cliente_endpoint(
    cliente_id: int,
    body: ClienteUpdateInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    request: __import__("fastapi").Request = None,  # type: ignore[assignment]
) -> Cliente:
    """Atualiza ficha do cliente (Fase 1.A enriquecida).

    Valida CPF/CNPJ/CEP/UF — campos inválidos retornam 422.
    Audit log automático: grava `cliente.update` com payload_diff.
    """
    cliente_atual = await _load_cliente_in_empresa(cliente_id, empresa_id)

    # Validações domínio BR
    cpf_norm = body.cpf
    if body.cpf is not None and body.cpf != "":
        if not is_valid_cpf(body.cpf):
            raise HTTPException(status_code=422, detail="CPF inválido")
        cpf_norm = normalize_cpf(body.cpf)

    cnpj_norm = body.cnpj
    if body.cnpj is not None and body.cnpj != "":
        if not is_valid_cnpj(body.cnpj):
            raise HTTPException(status_code=422, detail="CNPJ inválido")
        cnpj_norm = normalize_cnpj(body.cnpj)

    cep_norm = body.cep
    if body.cep is not None and body.cep != "":
        if not is_valid_cep(body.cep):
            raise HTTPException(status_code=422, detail="CEP inválido (8 dígitos)")
        cep_norm = normalize_cep(body.cep)

    uf_norm = body.uf
    if body.uf is not None and body.uf != "":
        if not is_valid_uf(body.uf):
            raise HTTPException(status_code=422, detail="UF inválida (2 chars BR)")
        uf_norm = body.uf.upper()

    # Aplica update
    pool = await get_pool()
    updated = await update_cliente_partial(
        pool,
        empresa_id,
        cliente_id,
        nome=body.nome,
        email=body.email,
        tipo_pessoa=body.tipo_pessoa or None,
        cpf=cpf_norm,
        cnpj=cnpj_norm,
        rg=body.rg,
        razao_social=body.razao_social,
        nome_fantasia=body.nome_fantasia,
        data_nascimento=body.data_nascimento,
        genero=body.genero,
        cep=cep_norm,
        logradouro=body.logradouro,
        numero=body.numero,
        complemento=body.complemento,
        bairro=body.bairro,
        cidade=body.cidade,
        uf=uf_norm,
        pais=body.pais,
        segmento=body.segmento,
        lifecycle_stage=body.lifecycle_stage or None,
        score=body.score,
        source=body.source,
        responsavel_user_id=body.responsavel_user_id,
        valor_estimado_brl=body.valor_estimado_brl,
        instagram=body.instagram,
        linkedin=body.linkedin,
        facebook=body.facebook,
        website=body.website,
        email_alternativo=body.email_alternativo,
        telefone_alternativo=body.telefone_alternativo,
        locale=body.locale,
        timezone=body.timezone,
        avatar_url=body.avatar_url,
        notes=body.notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    # Audit log com diff completo
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="cliente.update",
        entity_type="cliente",
        entity_id=str(cliente_id),
        payload_diff=diff_dicts(
            cliente_atual.model_dump(),
            updated.model_dump(),
        ),
        request=request,
    )
    logger.info(
        "cliente_updated",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        user_id=user_id,
    )
    return updated


@router.post("/{cliente_id}/anotacoes", status_code=201)
async def create_anotacao(
    cliente_id: int,
    body: AnotacaoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> ClienteAnotacao:
    """Adiciona anotação livre vinculada ao operador autenticado."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    out = await add_anotacao(pool, cliente_id, user_id, body.conteudo)
    logger.info(
        "cliente_anotacao_created",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        anotacao_id=out.id,
        user_id=user_id,
    )
    return out


@router.post("/{cliente_id}/tags", status_code=204)
async def create_tag(
    cliente_id: int,
    body: TagInput,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Adiciona tag ao cliente (idempotente — duplicata é silenciosa)."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    await add_tag(pool, cliente_id, body.tag)
    logger.info(
        "cliente_tag_added",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        tag=body.tag,
    )


@router.delete("/{cliente_id}/tags/{tag}", status_code=204)
async def delete_tag(
    cliente_id: int,
    tag: str,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Remove tag (idempotente — sem 404 quando não existe)."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    await remove_tag(pool, cliente_id, tag)
    logger.info(
        "cliente_tag_removed",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        tag=tag,
    )
