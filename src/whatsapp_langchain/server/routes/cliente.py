"""CRUD de Clientes do painel admin (M3 CRM Light).

Endpoints escopados pela empresa ativa via `get_empresa_context`.
Leitura exige `cliente.read[.own|.all]` e escrita `cliente.write[.own|.all]`
(até 24/09/2026 só a listagem checava permissão). Cadastro manual,
importação/exportação CSV e classificação do lead: mig 201.
"""

from __future__ import annotations

import io
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission_escopo
from whatsapp_langchain.shared.atendimento import list_atendimentos_by_cliente
from whatsapp_langchain.shared.audit import diff_dicts, record_audit
from whatsapp_langchain.shared.cliente import (
    ESTAGIOS_FUNIL,
    TEMPERATURAS,
    add_anotacao,
    add_tag,
    classificar_cliente,
    criar_cliente,
    get_cliente_by_id,
    list_anotacoes,
    list_clientes,
    remove_tag,
    tags_por_cliente,
    update_cliente_partial,
)
from whatsapp_langchain.shared.cliente_importacao import (
    MAX_BYTES_IMPORTACAO,
    email_valido,
    escrever_csv_clientes,
    ler_csv_clientes,
    normalizar_telefone_cadastro,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao
from whatsapp_langchain.shared.perfil import get_user_permissions
from whatsapp_langchain.shared.permissoes import (
    Scope,
    effective_scope,
    get_user_departamento_ids,
)
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


_PADRAO_ESTAGIO = r"^(lead|mql|sql|oportunidade|cliente|perdido)?$"
_PADRAO_TEMPERATURA = r"^(frio|morno|quente)?$"


async def _exigir(request: Request, user_id: str, empresa_id: int, base: str) -> Scope:
    """403 sem nenhuma variante de `base` (`X`, `X.own` ou `X.all`).

    Os perfis system só concedem as variantes com escopo — comparar o
    código-base exato tornaria a rota exclusiva do Admin.
    """
    perms = getattr(request.state, "_user_perms", None)
    if perms is None:
        perms = await get_user_permissions(await get_pool(), user_id, empresa_id)
        request.state._user_perms = perms
    scope = effective_scope(perms, base)
    if scope is None:
        raise HTTPException(
            status_code=403,
            detail="Seu perfil não tem acesso a esta ação nos clientes.",
        )
    return scope


async def _escopo_leitura(
    request: Request, user_id: str, empresa_id: int
) -> set[int] | None:
    """Departamentos visíveis para `cliente.read.own`; None = todos."""
    scope = await _exigir(request, user_id, empresa_id, "cliente.read")
    if scope == "own":
        return set(
            await get_user_departamento_ids(await get_pool(), user_id, empresa_id)
        )
    return None


@router.get("")
async def list_my_clientes(
    request: Request,
    search: str | None = Query(default=None, max_length=200),
    lifecycle_stage: str | None = Query(default=None, pattern=_PADRAO_ESTAGIO),
    temperatura: str | None = Query(default=None, pattern=_PADRAO_TEMPERATURA),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[Cliente]]:
    """Lista clientes da empresa ativa (mais recente primeiro).

    Sprint Governança RBAC (mig 083): aplica filtro record-level baseado
    em `cliente.read.own/all`. Operador (perm `.own`) só vê clientes que
    têm ao menos 1 atendimento em algum dos deptos vinculados ao user.
    Sem nenhuma das duas perms → 403.
    """
    scope_dept_ids = await _escopo_leitura(request, user_id, empresa_id)
    pool = await get_pool()

    rows = await list_clientes(
        pool,
        empresa_id,
        search=search,
        limit=limit,
        offset=offset,
        scope_departamento_ids=scope_dept_ids,
        lifecycle_stage=lifecycle_stage or None,
        temperatura=temperatura or None,
    )
    tags = await tags_por_cliente(pool, [c.id for c in rows])
    for c in rows:
        c.tags = tags.get(c.id, [])
    return {"clientes": rows}


class ClienteCreateInput(BaseModel):
    telefone: str = Field(min_length=8, max_length=30)
    nome: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=120)
    lifecycle_stage: str | None = Field(default=None, pattern=_PADRAO_ESTAGIO)
    temperatura: str | None = Field(default=None, pattern=_PADRAO_TEMPERATURA)


@router.post("", status_code=201)
async def create_cliente(
    request: Request,
    body: ClienteCreateInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
) -> Cliente:
    """Cadastro manual. Telefone já cadastrado → 409 com o id existente."""
    telefone = normalizar_telefone_cadastro(body.telefone)
    if telefone is None:
        raise HTTPException(
            status_code=422,
            detail="Telefone inválido. Use país e DDD, por exemplo 55 67 99999-0000.",
        )
    email = (body.email or "").strip() or None
    if email and not email_valido(email):
        raise HTTPException(status_code=422, detail="E-mail inválido.")
    pool = await get_pool()
    cliente, criado = await criar_cliente(
        pool,
        empresa_id,
        telefone,
        nome=(body.nome or "").strip() or None,
        email=email,
        source=(body.source or "").strip() or None,
    )
    if not criado:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Já existe um cliente com este telefone.",
                "cliente_id": cliente.id,
            },
        )
    if body.lifecycle_stage or body.temperatura:
        classificado = await classificar_cliente(
            pool,
            empresa_id,
            cliente.id,
            estagio=body.lifecycle_stage or None,
            temperatura=body.temperatura or None,
            pontuacao=None,
            origem="manual",
        )
        cliente = classificado or cliente
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="cliente.create",
        entity_type="cliente",
        entity_id=str(cliente.id),
        payload_diff={"origem": "manual"},
        request=request,
    )
    logger.info("cliente_criado_manual", empresa_id=empresa_id, cliente_id=cliente.id)
    return cliente


@router.post("/importar")
async def importar_clientes(
    request: Request,
    arquivo: UploadFile = File(...),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
) -> dict:
    """Importa clientes de um CSV (nome, telefone, email, origem).

    Telefone já cadastrado não é alterado (conta em `ja_existiam`). Linhas
    recusadas voltam com o número da linha e o motivo.
    """
    conteudo = await arquivo.read(MAX_BYTES_IMPORTACAO + 1)
    leitura = ler_csv_clientes(conteudo)
    if leitura.erro:
        raise HTTPException(status_code=422, detail=leitura.erro)
    pool = await get_pool()
    criados = 0
    ja_existiam = 0
    for linha in leitura.validas:
        _, criado = await criar_cliente(
            pool,
            empresa_id,
            linha.telefone,
            nome=linha.nome,
            email=linha.email,
            source=linha.origem,
        )
        if criado:
            criados += 1
        else:
            ja_existiam += 1
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="cliente.importar",
        entity_type="cliente",
        entity_id=None,
        payload_diff={
            "criados": criados,
            "ja_existiam": ja_existiam,
            "invalidos": len(leitura.invalidas),
        },
        request=request,
    )
    logger.info(
        "clientes_importados",
        empresa_id=empresa_id,
        criados=criados,
        ja_existiam=ja_existiam,
        invalidos=len(leitura.invalidas),
    )
    return {
        "criados": criados,
        "ja_existiam": ja_existiam,
        "invalidos": leitura.invalidas,
    }


_LIMITE_EXPORTACAO = 20_000


@router.get("/exportar")
async def exportar_clientes(
    request: Request,
    search: str | None = Query(default=None, max_length=200),
    lifecycle_stage: str | None = Query(default=None, pattern=_PADRAO_ESTAGIO),
    temperatura: str | None = Query(default=None, pattern=_PADRAO_TEMPERATURA),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> StreamingResponse:
    """CSV dos clientes com os mesmos filtros e escopo da listagem."""
    scope_dept_ids = await _escopo_leitura(request, user_id, empresa_id)
    pool = await get_pool()
    rows = await list_clientes(
        pool,
        empresa_id,
        search=search,
        limit=_LIMITE_EXPORTACAO,
        offset=0,
        scope_departamento_ids=scope_dept_ids,
        lifecycle_stage=lifecycle_stage or None,
        temperatura=temperatura or None,
    )
    tags = await tags_por_cliente(pool, [c.id for c in rows])
    linhas = [
        [
            c.nome,
            c.telefone,
            c.email,
            c.source,
            ESTAGIOS_FUNIL.get(c.lifecycle_stage or "", ""),
            TEMPERATURAS.get(c.temperatura or "", ""),
            c.score,
            ", ".join(tags.get(c.id, [])),
            c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "",
        ]
        for c in rows
    ]
    conteudo = escrever_csv_clientes(
        linhas,
        [
            "nome",
            "telefone",
            "email",
            "origem",
            "estagio",
            "temperatura",
            "pontuacao",
            "tags",
            "criado_em",
        ],
    )
    logger.info("clientes_exportados", empresa_id=empresa_id, linhas=len(linhas))
    fname = f"clientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> ClienteDetail:
    """Detalhe de um cliente — inclui tags (no objeto) e anotações."""
    await _exigir(request, user_id, empresa_id, "cliente.read")
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
    lifecycle_stage: str | None = Field(default=None, pattern=_PADRAO_ESTAGIO)
    temperatura: str | None = Field(default=None, pattern=_PADRAO_TEMPERATURA)
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
    _perm: None = Depends(require_permission_escopo("cliente.write")),
    request: Request = None,  # type: ignore[assignment]
) -> Cliente:
    """Atualiza dados do cliente (nome, email, endereço, etc.).

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
        temperatura=body.temperatura or None,
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


class ClassificacaoInput(BaseModel):
    """Classificação do lead salva pelo operador (vazio/None limpa)."""

    lifecycle_stage: str | None = Field(default=None, pattern=_PADRAO_ESTAGIO)
    temperatura: str | None = Field(default=None, pattern=_PADRAO_TEMPERATURA)
    score: int | None = Field(default=None, ge=0, le=100)


@router.put("/{cliente_id}/classificacao")
async def classificar_cliente_endpoint(
    cliente_id: int,
    body: ClassificacaoInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
) -> Cliente:
    """Salva ou confirma a classificação (vira `manual`; a IA não mexe mais)."""
    atual = await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    out = await classificar_cliente(
        pool,
        empresa_id,
        cliente_id,
        estagio=body.lifecycle_stage or None,
        temperatura=body.temperatura or None,
        pontuacao=body.score,
        origem="manual",
    )
    if out is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="cliente.classificar",
        entity_type="cliente",
        entity_id=str(cliente_id),
        payload_diff={
            "before": {
                "lifecycle_stage": atual.lifecycle_stage,
                "temperatura": atual.temperatura,
                "score": atual.score,
                "origem": atual.classificacao_origem,
            },
            "after": {
                "lifecycle_stage": out.lifecycle_stage,
                "temperatura": out.temperatura,
                "score": out.score,
                "origem": "manual",
            },
        },
        request=request,
    )
    logger.info(
        "cliente_classificado_manual", empresa_id=empresa_id, cliente_id=cliente_id
    )
    return out


@router.post("/{cliente_id}/anotacoes", status_code=201)
async def create_anotacao(
    cliente_id: int,
    body: AnotacaoInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
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
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
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
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission_escopo("cliente.write")),
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


@router.get("/{cliente_id}/atendimentos-anteriores")
async def list_atendimentos_anteriores(
    cliente_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    exclude_id: int | None = Query(default=None, ge=1),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Histórico de atendimentos do cliente (mais recente primeiro).

    Sprint 1.4 — painel cliente persistente no drawer. `exclude_id`
    omite o atendimento atual (UX: lista anteriores, não inclui o que
    o atendente já está vendo).

    Sem auth scope `.own/.all` aqui: o ato de poder ver o cliente
    (via _load_cliente_in_empresa) já implica direito a ver seu
    histórico no contexto do painel. Filtros por departamento ficam
    naturalmente aplicados via página de atendimento (`?dep_id=`).
    """
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    items = await list_atendimentos_by_cliente(
        pool,
        empresa_id,
        cliente_id,
        limit=limit,
        exclude_id=exclude_id,
    )
    return {"items": items}
