"""CRUD de Atendimentos do painel admin (M3 CRM Light).

A lista é paginada por **tipo de visualização** (`meus`, `aguardando`,
`grupos`, `outros`) — derivado em runtime, sem coluna no banco. As
mutações (`claim`, `close`, `transfer`) seguem o ciclo de vida descrito
em `shared/atendimento.py`.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.aba import (
    count_atendimentos_por_aba,
)
from whatsapp_langchain.shared.atendimento import (
    MARKERS_REPROCESSAVEIS,
    TipoVisualizacao,
    claim_atendimento,
    close_atendimento,
    devolver_atendimento_para_ia,
    get_atendimento_by_id,
    get_mensagem_midia,
    list_atendimento_mensagens,
    list_atendimentos,
    reenfileirar_mensagem,
    transfer_atendimento,
    transfer_atendimento_to_departamento,
)
from whatsapp_langchain.shared.atendimento_cleanup import (
    cleanup_zumbis,
    preview_zumbis,
)
from whatsapp_langchain.shared.atendimento_tag import (
    apply_tags_to_atendimento,
    list_atendimento_ids_com_tags,
    list_tags_de_atendimento,
)
from whatsapp_langchain.shared.atendimento_visualizacao import (
    marcar_lido,
    marcar_nao_lido,
)
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.conexao import get_conexao_by_id
from whatsapp_langchain.shared.conversa_ativa import (
    ConversaAtivaError,
    iniciar_conversa,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import (
    get_empresa_by_id,
    is_admin_of,
    is_conexao_scope_ativo,
)
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
from whatsapp_langchain.shared.models import Atendimento
from whatsapp_langchain.shared.nota_interna import create_nota_interna
from whatsapp_langchain.shared.outbound import (
    OutboundError,
    apagar_mensagem_enviada,
    editar_mensagem_enviada,
    send_outbound_manual,
    send_outbound_manual_midia,
    send_template_by_id,
)
from whatsapp_langchain.shared.perfil import get_user_permissions
from whatsapp_langchain.shared.permissoes import (
    effective_scope,
    get_user_conexao_ids,
    get_user_departamento_ids,
)
from whatsapp_langchain.shared.queue import reset_thread_checkpoint
from whatsapp_langchain.shared.transcricao import (
    MensagemSemAudioError,
    transcrever_mensagem,
)
from whatsapp_langchain.shared.variavel import build_render_context, render_template
from whatsapp_langchain.shared.whitelist import is_whitelisted


async def _resolve_perms_cached(
    request: Request, user_id: str, empresa_id: int
) -> set[str]:
    """Cache de permissões por request — evita N queries quando handler
    chama effective_scope várias vezes."""
    cached = getattr(request.state, "_user_perms", None)
    if cached is not None:
        return cached
    pool = await get_pool()
    perms = await get_user_permissions(pool, user_id, empresa_id)
    request.state._user_perms = perms
    return perms


logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/atendimentos",
    tags=["atendimentos"],
    dependencies=[Depends(verify_service_token)],
)


# Importado de `shared`, não redeclarado: a lista estava duplicada aqui e lá, e
# duas cópias de um Literal divergem sem ninguém notar — o FastAPI valida contra
# esta, o SQL filtra pela outra.


class CloseInput(BaseModel):
    status: Literal["resolvido", "abandonado"] = "resolvido"


class IniciarConversaInput(BaseModel):
    """Conversa ativa (mig 170): exatamente um de `mensagem` OU `template_id`.

    Evolution envia texto livre; WABA exige template aprovado (a
    validação por provider mora em `shared/conversa_ativa.py`).
    """

    telefone: str = Field(min_length=8, max_length=32)
    #: Omitido = conexão padrão da empresa (mig 170).
    conexao_id: int | None = None
    mensagem: str | None = Field(default=None, max_length=4096)
    template_id: int | None = None
    variaveis: dict[str, str] | None = None
    nome: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _exactly_one(self) -> IniciarConversaInput:
        if bool((self.mensagem or "").strip()) == bool(self.template_id):
            raise ValueError("Informe exatamente um: mensagem OU template_id")
        return self


class TransferInput(BaseModel):
    """Aceita exatamente um destino: atendente (user_id) ou departamento."""

    user_id: str | None = None
    departamento_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> TransferInput:
        if bool(self.user_id) == bool(self.departamento_id):
            raise ValueError("Informe exatamente um: user_id OU departamento_id")
        return self


class ResponderInput(BaseModel):
    conteudo: str


class ApplyTagsInput(BaseModel):
    """Delta de tags em um atendimento."""

    add: list[int] = []
    remove: list[int] = []


class NotaInternaInput(BaseModel):
    """Texto de nota interna (msg privada na timeline da equipe)."""

    texto: str = Field(min_length=1, max_length=4000)


@router.get("")
async def list_my_atendimentos(
    request: Request,
    tipo: TipoVisualizacao = Query(default="nao_resolvidas"),
    dep_id: int | None = Query(default=None, ge=1),
    prioridade: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    aba_id: int | None = Query(default=None, ge=1),
    tag_id: list[int] | None = Query(
        default=None, description="Filter por tag(s) OR — multi-valor"
    ),
    assigned_to: str | None = Query(
        default=None, max_length=64, description="Filtra pelo responsável"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[Atendimento]]:
    """Lista atendimentos da empresa filtrados pelo tipo (4 abas) +
    filtros opcionais Sprint F.2: departamento, prioridade, busca em
    cliente.nome/atendimento.protocolo.

    Sprint Governança RBAC (mig 083): aplica filtro record-level baseado
    em `atendimento.read.own/all`. Operador (perm `.own`) só vê
    atendimentos do(s) depto(s) vinculado(s) a ele em
    `usuario_departamento`. Sem nenhuma das duas perms → 403.
    """
    if prioridade is not None and prioridade not in (
        "baixa",
        "media",
        "alta",
        "urgente",
    ):
        raise HTTPException(status_code=400, detail="prioridade inválida")
    pool = await get_pool()
    # Resolve scope record-level ANTES da query
    perms = await _resolve_perms_cached(request, user_id, empresa_id)
    scope = effective_scope(perms, "atendimento.read")
    if scope is None:
        raise HTTPException(
            status_code=403,
            detail="Permissão necessária: atendimento.read[.own|.all]",
        )
    scope_dept_ids: set[int] | None = None
    scope_conexao_ids: set[int] | None = None
    if scope == "own":
        dept_ids = await get_user_departamento_ids(pool, user_id, empresa_id)
        # Set vazio = sem deptos vinculados → list_atendimentos retorna []
        scope_dept_ids = set(dept_ids)
        # ADR-002 Etapa 4 — só entra em jogo se a EMPRESA optou (default OFF).
        if await is_conexao_scope_ativo(pool, empresa_id):
            conexao_ids = await get_user_conexao_ids(
                pool, user_id, empresa_id, contexto="fila"
            )
            scope_conexao_ids = set(conexao_ids)

    # Filtro por tag (OR): resolve IDs de atendimentos que têm qualquer tag
    only_ids: list[int] | None = None
    if tag_id:
        only_ids = await list_atendimento_ids_com_tags(
            pool, empresa_id=empresa_id, tag_ids=tag_id
        )

    rows = await list_atendimentos(
        pool,
        empresa_id,
        tipo=tipo,
        current_user_id=user_id,
        limit=limit,
        offset=offset,
        dep_id=dep_id,
        prioridade=prioridade,
        q=q,
        aba_id=aba_id,
        only_ids=only_ids,
        scope_departamento_ids=scope_dept_ids,
        scope_conexao_ids=scope_conexao_ids,
        assigned_to_user_id=assigned_to,
    )
    return {"atendimentos": rows}


@router.post("/iniciar", status_code=201)
async def iniciar_conversa_endpoint(
    body: IniciarConversaInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.iniciar")),
) -> dict:
    """Conversa ativa 1:1 (mig 170) — operador inicia contato com um número.

    Cria (ou anexa a) atendimento `iniciado_cliente=false`, nascendo
    `em_andamento` e ATRIBUÍDO a quem iniciou — a IA fica calada pelo gate de
    handoff. Compliance do disparo se aplica (opt-out 409, teto diário 409).
    Nasce `em_andamento`, então o auto-abandono de `aguardando>48h` do
    cleanup não mata a conversa enquanto o cliente não responde.
    """
    pool = await get_pool()
    try:
        atendimento, was_created = await iniciar_conversa(
            pool,
            empresa_id=empresa_id,
            user_id=user_id,
            conexao_id=body.conexao_id,
            telefone=body.telefone,
            mensagem=body.mensagem,
            template_id=body.template_id,
            variaveis=body.variaveis,
            nome=body.nome,
        )
    except ConversaAtivaError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e

    if was_created:
        await dispatch_event(
            pool,
            empresa_id,
            "atendimento.aberto",
            {
                "atendimento_id": atendimento.id,
                "cliente_id": atendimento.cliente_id,
                "conexao_id": atendimento.conexao_id,
                "agente_atual": atendimento.agente_atual,
                "iniciado_cliente": False,
                "iniciado_por_user_id": user_id,
            },
        )
    # Nasce atribuída a quem criou — o selo correto sem re-derivar a página.
    atendimento.situacao = "em_atendimento"
    return {
        "ok": True,
        "was_created": was_created,
        "atendimento": atendimento.model_dump(mode="json"),
    }


@router.get("/contadores")
async def list_contadores(
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Contadores pra badges da sidebar (sistema + abas do user).

    Usa as mesmas semânticas de scope record-level que `list_atendimentos`.
    Sem cache — query é leve (COUNT com index). Frontend chama a cada
    SSE event `aba_count_changed` (também a cada 30s como fallback).
    """
    pool = await get_pool()
    perms = await _resolve_perms_cached(request, user_id, empresa_id)
    scope = effective_scope(perms, "atendimento.read")
    if scope is None:
        # Sem perm: zero pra todos (sidebar fica vazia, não 403)
        return {
            "sistema": {
                "aguardando": 0,
                "meus": 0,
                "outros": 0,
                "humano_solicitado": 0,
                "nao_lidas": 0,
            },
            "abas": {},
        }
    dept_filter_sql = ""
    dept_filter_args: list = []
    conexao_filter_sql = ""
    conexao_filter_args: list = []
    if scope == "own":
        dept_ids = await get_user_departamento_ids(pool, user_id, empresa_id)
        if not dept_ids:
            return {
                "sistema": {
                    "aguardando": 0,
                    "meus": 0,
                    "outros": 0,
                    "humano_solicitado": 0,
                    "nao_lidas": 0,
                },
                "abas": {},
            }
        dept_filter_sql = " AND departamento_id = ANY(%s)"
        dept_filter_args = [list(dept_ids)]
        # ADR-002 Etapa 4 — mesmo filtro do `list_atendimentos`. Sem isto o
        # badge da sidebar contaria atendimento que a lista não mostra
        # (gotcha_contagem_por_endpoint_permissao: contagem por endpoint
        # falha calada quando não espelha o mesmo escopo).
        if await is_conexao_scope_ativo(pool, empresa_id):
            conexao_ids = await get_user_conexao_ids(
                pool, user_id, empresa_id, contexto="fila"
            )
            if not conexao_ids:
                return {
                    "sistema": {
                        "aguardando": 0,
                        "meus": 0,
                        "outros": 0,
                        "humano_solicitado": 0,
                        "nao_lidas": 0,
                    },
                    "abas": {},
                }
            conexao_filter_sql = " AND conexao_id = ANY(%s)"
            conexao_filter_args = [list(conexao_ids)]

    async with pool.connection() as conn:
        # Sistema. As 3 primeiras são as abas antigas (o APK instalado ainda as
        # usa); `humano_solicitado` é a única aba nova com badge além de
        # "Não Lidas" — no Chatvolt só essas duas têm contador, e badge em toda
        # aba vira ruído em vez de sinal.
        cur = await conn.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE status = 'aguardando'),
                COUNT(*) FILTER (WHERE status = 'em_andamento'
                                  AND assigned_to_user_id = %s),
                COUNT(*) FILTER (WHERE status IN ('aguardando', 'em_andamento')
                                  AND (assigned_to_user_id IS NULL
                                       OR assigned_to_user_id <> %s)),
                COUNT(*) FILTER (WHERE status = 'aguardando'
                                  AND departamento_id IS NOT NULL
                                  AND assigned_to_user_id IS NULL)
              FROM atendimento
             WHERE empresa_id = %s{dept_filter_sql}{conexao_filter_sql}
            """,
            (user_id, user_id, empresa_id, *dept_filter_args, *conexao_filter_args),
        )
        sys_row = await cur.fetchone() or (0, 0, 0, 0)

        # Não lidas: conversas com ALGUMA mensagem do cliente após a última vez
        # que este usuário abriu. EXISTS em vez de contar mensagens — a aba
        # mostra quantas CONVERSAS esperam leitura, não quantas mensagens.
        cur = await conn.execute(
            f"""
            SELECT COUNT(*)
              FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.status IN ('aguardando', 'em_andamento'){dept_filter_sql}{conexao_filter_sql}
               AND EXISTS (
                   SELECT 1 FROM message_queue m
                     LEFT JOIN atendimento_visualizacao v
                            ON v.atendimento_id = m.atendimento_id
                           AND v.user_id = %s
                    WHERE m.atendimento_id = a.id
                      AND m.status = 'done'
                      AND m.incoming_message IS NOT NULL
                      AND m.incoming_message <> ''
                      AND COALESCE(m.interna, FALSE) = FALSE
                      AND (v.ultima_visualizacao_at IS NULL
                           OR m.created_at > v.ultima_visualizacao_at))
            """,
            (empresa_id, *dept_filter_args, *conexao_filter_args, user_id),
        )
        nao_lidas = (await cur.fetchone() or (0,))[0]

    # Contadores por aba (sempre do próprio user — abas são pessoais)
    por_aba = await count_atendimentos_por_aba(
        pool, user_id=user_id, empresa_id=empresa_id
    )
    return {
        "sistema": {
            # Antigas (o APK instalado ainda lê estas):
            "aguardando": sys_row[0],
            "meus": sys_row[1],
            "outros": sys_row[2],
            # Novas — as duas únicas abas com badge, como no Chatvolt:
            "humano_solicitado": sys_row[3],
            "nao_lidas": nao_lidas,
        },
        "abas": {str(k): v for k, v in por_aba.items()},
        # `sem_aba` some com a mig 150: conversa não "pertence" mais a uma aba,
        # então "sem aba" seria o total da empresa — número que não informa nada.
    }


async def _load_atendimento_in_empresa(
    atendimento_id: int, empresa_id: int
) -> Atendimento:
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    if atd.empresa_id != empresa_id:
        raise HTTPException(
            status_code=403, detail="Atendimento fora da empresa ativa."
        )
    return atd


# ---- SSE ----
#
# ATENÇÃO: `/events` tem que vir ANTES de `/{atendimento_id}` — o FastAPI casa
# rotas na ordem de registro, e `/{atendimento_id}` engoliria `/events` (daria
# 422 tentando converter "events" em int). Mesmo motivo de `/contadores` acima.


def _sse_stream(
    *, empresa_id: int, atendimento_id: int | None = None
) -> StreamingResponse:
    """Stream SSE do canal Postgres `atendimento_event` (triggers da mig 035).

    Um filtro obrigatório e um opcional:
    - `empresa_id` SEMPRE filtra. O canal LISTEN é global no Postgres, então
      sem isso um cliente receberia evento de todos os tenants. O payload passou
      a carregar `empresa_id` na mig 145 exatamente pra permitir esse filtro.
    - `atendimento_id`, quando dado, restringe a uma conversa (uso do drawer
      web). Sem ele, é o stream da empresa inteira (uso da lista no app).

    Não abre conexão própria: assina o `NotifyHub` do canal — UM `LISTEN` por
    processo, fan-out em memória (decisão 6 do ADR-003; antes era uma conexão
    de banco por stream aberto, o gargalo de capacidade M3).

    Heartbeat a cada 25s pra sobreviver ao Traefik (idle timeout default 60s).
    Se o hub reconectar ao Postgres, reemite `connected`: o cliente trata como
    "ressincronize" (o drawer recarrega a timeline nesse evento).
    """
    import asyncio
    import json

    from whatsapp_langchain.shared.notify_hub import RESYNC, get_hub

    escopo = {"empresa_id": empresa_id}
    if atendimento_id is not None:
        escopo["atendimento_id"] = atendimento_id
    conectado = f"event: connected\ndata: {json.dumps(escopo)}\n\n"

    async def event_generator():
        hub = get_hub("atendimento_event")
        try:
            async with hub.subscribe() as assinatura:
                if not await hub.esperar_conexao():
                    raise RuntimeError("LISTEN não conectou em 10s")
                yield conectado
                while True:
                    try:
                        bruto = await assinatura.get(timeout=25)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if bruto == RESYNC:
                        yield conectado
                        continue
                    try:
                        payload = json.loads(bruto)
                    except (ValueError, TypeError):
                        continue
                    # Isolamento de tenant. Payload sem empresa_id vem de
                    # trigger anterior à mig 145 — descarta em vez de
                    # entregar sem saber de quem é.
                    if payload.get("empresa_id") != empresa_id:
                        continue
                    if (
                        atendimento_id is not None
                        and payload.get("atendimento_id") != atendimento_id
                    ):
                        continue
                    evt_name = payload.get("event", "update")
                    yield f"event: {evt_name}\ndata: {bruto}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sse_atendimento_failed",
                empresa_id=empresa_id,
                atendimento_id=atendimento_id,
                error=str(exc),
            )
            yield f"event: error\ndata: {json.dumps({'error': str(exc)[:200]})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events")
async def sse_events_empresa(
    empresa_id: int = Depends(get_empresa_context),
) -> StreamingResponse:
    """Stream de eventos de TODOS os atendimentos da empresa ativa.

    Existe pro app móvel manter a lista de conversas viva com UMA conexão. O
    stream por atendimento (`/{id}/events`) continua servindo o drawer web.
    """
    return _sse_stream(empresa_id=empresa_id)


@router.get("/{atendimento_id}")
async def read_atendimento(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Atendimento:
    """Detalhe — inclui cliente_nome/cliente_telefone via JOIN."""
    return await _load_atendimento_in_empresa(atendimento_id, empresa_id)


@router.get("/{atendimento_id}/events")
async def sse_events(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> StreamingResponse:
    """Stream de eventos de UM atendimento via SSE.

    Substitui o polling 3s do AtendimentoDrawer. Valida o acesso ANTES de abrir
    o stream (4xx imediato se negado) e delega pro `_sse_stream`, que é o mesmo
    gerador usado pelo stream de empresa.

    Frontend acessa via Next.js API route proxy (/api/sse/...) que adiciona
    Authorization + X-User-Id headers — EventSource nativo não suporta headers
    custom. O app móvel usa OkHttp, que suporta, e fala direto com esta rota.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    return _sse_stream(empresa_id=empresa_id, atendimento_id=atendimento_id)


@router.get("/{atendimento_id}/mensagens")
async def read_atendimento_mensagens(
    atendimento_id: int,
    limit: int = Query(default=200, ge=1, le=500),
    before_id: int | None = Query(
        default=None,
        ge=1,
        description="Cursor: devolve mensagens anteriores a este id (histórico).",
    ),
    incluir_midia: bool = Query(
        default=True,
        description=(
            "False devolve só `media_disponivel` em vez do conteúdo base64; "
            "busque os bytes em /mensagens/{id}/midia. Reduz a resposta de "
            "dezenas de MB pra alguns KB em conversas com anexo."
        ),
    ),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Mensagens do atendimento em ordem cronológica (ASC), da mais recente.

    Devolve as ÚLTIMAS `limit` mensagens. Pra carregar histórico, repita a
    chamada passando `before_id=next_cursor` — é o que o Paging 3 do app usa
    pra rolar pra cima sem fim. `next_cursor` vem null quando não há mais nada
    antes.

    Cobre só mensagens com `atendimento_id` preenchido — inbound antigas
    (anteriores ao M3) ficam fora; o histórico legado segue acessível
    pela rota `/api/chats/{phone}` se for preciso.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    mensagens = await list_atendimento_mensagens(
        pool,
        atendimento_id,
        empresa_id,
        limit=limit,
        before_id=before_id,
        incluir_midia=incluir_midia,
    )
    # Página cheia sugere que há mais atrás; o cursor é o menor id devolvido
    # (as mensagens vêm ASC, então é o primeiro). Página incompleta = fim.
    next_cursor = mensagens[0]["id"] if len(mensagens) == limit else None
    return {
        "atendimento_id": atendimento_id,
        "mensagens": mensagens,
        "next_cursor": next_cursor,
    }


@router.post("/{atendimento_id}/mensagens/{mensagem_id}/transcrever")
async def transcrever_mensagem_audio(
    atendimento_id: int,
    mensagem_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Transcreve sob demanda a nota de voz de UMA mensagem (mig 169).

    Preenche `message_queue.transcricao` — texto pro OPERADOR, independente
    do agente IA. Idempotente: mensagem já transcrita devolve o texto salvo
    sem nova chamada de LLM. Escopo por empresa (quem vê a conversa pode
    transcrever); custa uma chamada de LLM por áudio novo.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    try:
        texto = await transcrever_mensagem(
            pool,
            mensagem_id,
            empresa_id=empresa_id,
            atendimento_id=atendimento_id,
        )
    except MensagemSemAudioError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Falha de provedor (OpenRouter fora, timeout): transitória — o
        # operador tenta de novo pelo mesmo botão.
        logger.warning(
            "transcricao_manual_falhou",
            atendimento_id=atendimento_id,
            mensagem_id=mensagem_id,
            actor_user_id=user_id,
            erro=type(e).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Não foi possível transcrever agora. Tente novamente.",
        ) from e
    logger.info(
        "transcricao_manual_ok",
        atendimento_id=atendimento_id,
        mensagem_id=mensagem_id,
        actor_user_id=user_id,
    )
    return {"ok": True, "mensagem_id": mensagem_id, "transcricao": texto}


class EditarMensagemInput(BaseModel):
    """Texto novo de uma mensagem já entregue."""

    texto: str = Field(min_length=1, max_length=4096)


@router.patch("/{atendimento_id}/mensagens/{mensagem_id}/texto")
async def editar_mensagem(
    atendimento_id: int,
    mensagem_id: int,
    body: EditarMensagemInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> dict:
    """Corrige no WhatsApp do cliente uma mensagem que o operador enviou (mig 172).

    Vale só para o que saiu pelo painel/app: `shared/outbound.py` guarda a
    chave devolvida pelo provedor, enquanto o worker descarta a das respostas
    da IA — então mensagem de agente não é editável, por falta de endereço.

    Janela de 15 minutos, imposta pelo WhatsApp. A regra completa mora em
    `shared/atendimento.avaliar_alteracao_resposta` e é revalidada aqui: a UI
    esconde o que não pode, mas entre a tela carregar e o toque acontecer a
    janela vira.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    try:
        await editar_mensagem_enviada(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            mensagem_id=mensagem_id,
            texto=body.texto,
        )
    except OutboundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info(
        "mensagem_editada_ok",
        atendimento_id=atendimento_id,
        mensagem_id=mensagem_id,
        actor_user_id=user_id,
    )
    return {"ok": True, "mensagem_id": mensagem_id, "texto": body.texto}


@router.delete("/{atendimento_id}/mensagens/{mensagem_id}/texto")
async def apagar_mensagem(
    atendimento_id: int,
    mensagem_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> dict:
    """Apaga para todos, no WhatsApp, uma mensagem que o operador enviou (mig 172).

    Mesmas pré-condições da edição, com janela bem maior (~2 dias; cortamos em
    48h por segurança). Do nosso lado é soft delete: o texto fica no banco para
    auditoria e a timeline passa a mostrar "Mensagem apagada".
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    try:
        await apagar_mensagem_enviada(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            mensagem_id=mensagem_id,
        )
    except OutboundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info(
        "mensagem_apagada_ok",
        atendimento_id=atendimento_id,
        mensagem_id=mensagem_id,
        actor_user_id=user_id,
    )
    return {"ok": True, "mensagem_id": mensagem_id}


@router.get("/{atendimento_id}/mensagens/{mensagem_id}/midia")
async def read_mensagem_midia(
    atendimento_id: int,
    mensagem_id: int,
    lado: Literal["in", "out"] = Query(
        default="in",
        description="`in` = mídia que o cliente mandou; `out` = a que o operador mandou.",
    ),
    empresa_id: int = Depends(get_empresa_context),
) -> Response:
    """Serve UMA mídia da conversa, decodificada.

    Existe pro cliente não precisar baixar a conversa inteira com os anexos
    embutidos: com `/mensagens?incluir_midia=false` a lista fica pequena e cada
    mídia vem por aqui, quando (e se) for renderizada.

    Medido em produção antes disto: um PDF ocupa 5 MB numa linha de
    `message_queue`, e `/mensagens?limit=50` devolvia tudo inline — no 4G do
    celular, a conversa simplesmente não abria.

    `Cache-Control: private` porque a resposta é conteúdo de um cliente
    específico: pode ficar no cache do aparelho, nunca num cache compartilhado.
    `immutable` é honesto aqui — mídia de mensagem não muda depois de recebida.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    midia = await get_mensagem_midia(
        pool,
        mensagem_id=mensagem_id,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        lado=lado,
    )
    if midia is None:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")

    dados, mime = midia
    return Response(
        content=dados,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


@router.post("/{atendimento_id}/claim")
async def claim(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission("atendimento.claim")),
) -> Atendimento:
    """Operador "puxa" o atendimento — vira em_andamento + assigned=user.

    Sprint G.3 — valida capacidade: 409 se user já tem >= max_paralelos
    atendimentos abertos. Default max=5 (mig 062).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    # Capacidade — só checa se user NÃO está claim-ando o atendimento atual
    # (caso edge de re-claim de algo que ele já tem).
    from whatsapp_langchain.shared.atendente import (
        count_atendimentos_user_abertos,
        get_max_paralelos,
    )

    count = await count_atendimentos_user_abertos(pool, user_id, empresa_id)
    max_paralelos = await get_max_paralelos(pool, user_id)
    if count >= max_paralelos:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Você já está atendendo {count} de {max_paralelos} atendimentos. "
                "Encerre algum antes de assumir mais."
            ),
        )
    out = await claim_atendimento(pool, atendimento_id, user_id)
    if out is None:
        # Já foi fechado entre o load e o claim (race) — sinaliza conflito.
        raise HTTPException(
            status_code=409, detail="Atendimento já fechado, não pode ser claimed."
        )
    logger.info(
        "atendimento_claimed",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        user_id=user_id,
    )
    # Aviso ao cliente ("Você foi transferido para o atendente *X*", Sprint E.3)
    # passou a ser OPCIONAL por empresa na mig 147, com default FALSE.
    #
    # Antes era sempre enviado. Não serve pro modelo co-piloto — a IA responde e
    # o operador entra e sai da conversa quando quer, então anunciar cada entrada
    # expõe mecânica interna que não muda nada pro cliente, e com o botão no
    # celular um toque errado virava mensagem. Continua disponível pra operação
    # de fila clássica, onde o cliente esperava e passa a falar com uma pessoa.
    empresa = await get_empresa_by_id(pool, empresa_id)
    if empresa is not None and empresa.anuncia_atendente_assumiu:
        # Best-effort: falha no envio não desfaz o claim.
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    'SELECT name FROM auth."user" WHERE id = %s',
                    (user_id,),
                )
                row = await cur.fetchone()
            nome_atendente = (row[0] if row else None) or "atendente"
            from whatsapp_langchain.shared.outbound import send_system_outbound

            await send_system_outbound(
                pool,
                atendimento_id=atendimento_id,
                empresa_id=empresa_id,
                conteudo=f"Você foi transferido para o atendente *{nome_atendente}*.",
                tag_user_id=f"system:claim:{user_id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "claim_outbound_failed",
                atendimento_id=atendimento_id,
                error=str(exc),
            )

    # Evento interno sai sempre: quem precisa saber é a equipe, não o cliente.
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.atendido",
        {
            "atendimento_id": atendimento_id,
            "assigned_to_user_id": user_id,
            "cliente_id": out.cliente_id,
        },
    )
    return out


@router.post("/{atendimento_id}/devolver-ia")
async def devolver_ia(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> Atendimento:
    """Devolve o atendimento pra IA: desfaz o "Atender".

    Existe porque assumir era **irreversível**. O worker cala o agente quando o
    atendimento está `em_andamento` com dono, e as duas saídas que havia —
    `close` (dispara pesquisa de satisfação) e `transfer` (avisa o cliente que
    mudou de setor) — falam com o cliente. Nenhuma serve pra corrigir um toque
    errado, e num celular o toque errado é fácil.

    **Nada é enviado ao cliente**, ao contrário do `claim` (que anuncia o
    atendente) e do `transfer`. Do lado dele, a IA simplesmente volta a
    responder.

    409 se o atendimento já está fechado: devolvê-lo pra fila o reabriria por
    cima de quem encerrou.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    out = await devolver_atendimento_para_ia(pool, atendimento_id)
    if out is None:
        raise HTTPException(
            status_code=409,
            detail="Atendimento já fechado — não pode voltar para a fila da IA.",
        )
    logger.info(
        "atendimento_devolvido_para_ia",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        user_id=user_id,
    )
    return out


@router.post("/{atendimento_id}/close")
async def close(
    atendimento_id: int,
    body: CloseInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission("atendimento.close")),
) -> Atendimento:
    """Fecha atendimento. status='resolvido' (default) ou 'abandonado'."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    out = await close_atendimento(pool, atendimento_id, status=body.status)
    if out is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    logger.info(
        "atendimento_closed",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        status=body.status,
        user_id=user_id,
    )
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.fechado",
        {
            "atendimento_id": atendimento_id,
            "status": body.status,
            "closed_by_user_id": user_id,
            "cliente_id": out.cliente_id,
        },
    )
    # Sprint Y fix: dispara CSAT se a empresa tiver csat_ativo=true.
    # Best-effort — falha aqui não bloqueia o close.
    if body.status == "resolvido":
        from whatsapp_langchain.shared.avaliacao import trigger_csat_se_ativo

        await trigger_csat_se_ativo(pool, empresa_id, atendimento_id)
    return out


@router.post("/{atendimento_id}/responder")
async def responder(
    atendimento_id: int,
    body: ResponderInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Envia mensagem manual do operador.

    O atendimento precisa estar `aguardando` ou `em_andamento`. A mensagem
    é persistida em message_queue como row outbound-only — aparece na
    timeline do drawer junto às mensagens do agente IA.

    Antes do envio, `{{empresa.*}}`, `{{cliente.*}}`, `{{data.*}}` e
    `{{var.*}}` são resolvidos server-side (M5.d) — operador pode digitar
    `Olá {{cliente.nome}}!` direto e o cliente recebe o texto final.
    """
    pool = await get_pool()
    ctx = await build_render_context(pool, empresa_id, atendimento_id=atendimento_id)
    rendered = render_template(body.conteudo, ctx)
    try:
        row = await send_outbound_manual(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            user_id=user_id,
            conteudo=rendered,
        )
    except OutboundError as e:
        # Mapeia para 4xx — erros lógicos (atendimento fechado, etc).
        msg = str(e)
        status_code = 409 if "fechado" in msg else 404 if "encontrad" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg) from e
    return {"mensagem": row}


#: MIMEs aceitos no anexo do operador.
#:
#: Allowlist e não denylist: o arquivo vai pro WhatsApp de um cliente real, e o
#: conjunto do que faz sentido mandar num atendimento é pequeno e conhecido.
#: `audio/*` cobre o que o app grava (OGG/Opus) e o que outros aparelhos gravam.
MIDIA_MIMES_ACEITOS = (
    "audio/",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-excel",
    "text/plain",
)


@router.post("/{atendimento_id}/responder-midia")
async def responder_midia(
    atendimento_id: int,
    arquivo: UploadFile = File(...),
    legenda: str = Form(""),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> dict:
    """Envia anexo ou nota de voz do operador ao cliente.

    Contraparte de `responder` para o que não é texto: o app Android grava áudio
    e anexa foto/documento por aqui. Áudio chega como nota de voz (bolha com
    player), o resto como anexo.

    A legenda passa pelo mesmo render de `{{cliente.*}}` do texto — o operador
    pode legendar uma foto com `Olá {{cliente.nome}}` e o cliente recebe o nome.

    Só conexões Evolution suportam mídia hoje; WABA devolve 400 com a
    razão, em vez de aceitar o upload e não entregar nada.
    """
    mime = (arquivo.content_type or "").lower()
    if not mime.startswith(MIDIA_MIMES_ACEITOS):
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não suportado: {mime or 'desconhecido'}.",
        )

    conteudo = await arquivo.read()

    pool = await get_pool()
    ctx = await build_render_context(pool, empresa_id, atendimento_id=atendimento_id)
    try:
        row = await send_outbound_manual_midia(
            pool,
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            user_id=user_id,
            arquivo=conteudo,
            mime=mime,
            filename=arquivo.filename,
            legenda=render_template(legenda, ctx),
        )
    except OutboundError as e:
        msg = str(e)
        status_code = 409 if "fechado" in msg else 404 if "encontrad" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg) from e
    return {"mensagem": row}


class SendTemplateInput(BaseModel):
    template_id: int
    variaveis: dict[str, str] = Field(default_factory=dict)


@router.post("/{atendimento_id}/send-template")
async def send_template(
    atendimento_id: int,
    body: SendTemplateInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> dict:
    """Envia um template HSM **aprovado** ao cliente do atendimento.

    Útil pra reabrir conversa fora da janela 24h (no WhatsApp oficial só
    template é permitido). Roteia por provider e persiste na
    timeline do drawer.
    """
    atd = await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    cliente = await get_cliente_by_id(pool, atd.cliente_id)
    if cliente is None or cliente.empresa_id != empresa_id:
        raise HTTPException(
            status_code=404, detail="Cliente do atendimento não encontrado."
        )
    if atd.conexao_id is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "A conexão deste atendimento foi removida — reatribua a uma "
                "conexão ativa para enviar."
            ),
        )
    try:
        res = await send_template_by_id(
            pool,
            conexao_id=atd.conexao_id,
            empresa_id=empresa_id,
            to=cliente.telefone,
            template_id=body.template_id,
            variables=body.variaveis,
            atendimento_id=atendimento_id,
            user_id=user_id,
        )
    except OutboundError as e:
        msg = str(e)
        status_code = 404 if "encontrad" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg) from e
    return {
        "mensagem": res.get("message_row"),
        "provider_message_id": res["provider_message_id"],
    }


@router.post("/{atendimento_id}/transfer")
async def transfer(
    atendimento_id: int,
    body: TransferInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission("atendimento.transfer")),
) -> Atendimento:
    """Transfere o atendimento — modo `user_id` (atribui a outro operador,
    mantém em_andamento) OU modo `departamento_id` (limpa atendente, volta
    pra status=aguardando = entra na fila do depto).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()

    departamento_nome: str | None = None
    if body.departamento_id is not None:
        out = await transfer_atendimento_to_departamento(
            pool, atendimento_id, body.departamento_id
        )
        if out is None:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT nome FROM departamento WHERE id = %s AND empresa_id = %s",
                (body.departamento_id, empresa_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Departamento não encontrado.")
        departamento_nome = row[0]

        # Notifica o cliente via WhatsApp — best-effort. Falha não bloqueia
        # a transferência (atendimento já foi atualizado no DB).
        try:
            await send_outbound_manual(
                pool,
                atendimento_id=atendimento_id,
                empresa_id=empresa_id,
                user_id=user_id,
                conteudo=(
                    f"Você foi transferido para o setor *{departamento_nome}*. "
                    "Em breve um atendente entrará em contato. 😊"
                ),
            )
        except OutboundError as exc:
            logger.warning(
                "transfer_notify_failed",
                atendimento_id=atendimento_id,
                empresa_id=empresa_id,
                departamento_id=body.departamento_id,
                error=str(exc),
            )
    else:
        assert body.user_id is not None  # validator garante
        out = await transfer_atendimento(pool, atendimento_id, body.user_id)
        if out is None:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado.")

    logger.info(
        "atendimento_transferred",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        from_user=user_id,
        to_user=body.user_id,
        to_departamento=body.departamento_id,
    )
    # Payload unificado entre tool (IA) e endpoint manual — mesmo schema.
    await dispatch_event(
        pool,
        empresa_id,
        "atendimento.transferido",
        {
            "atendimento_id": atendimento_id,
            "from_user_id": user_id,
            "to_user_id": body.user_id,
            "departamento_id": out.departamento_id,
            "departamento_nome": departamento_nome,
            "prioridade": out.prioridade,
            "classificacao": out.classificacao,
            "sentimento": out.sentimento,
            "resumo_ia": out.resumo_ia,
            "cliente_id": out.cliente_id,
            "cliente_nome": out.cliente_nome,
            "phone": out.cliente_telefone,
            "protocolo": out.protocolo,
            "motivo": None,
            "iniciado_por": "humano",
            "agente_slug": None,
        },
    )
    return out


@router.post("/{atendimento_id}/reset-thread")
async def reset_thread(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _perm: None = Depends(require_permission("atendimento.reset_thread")),
) -> dict:
    """Apaga checkpoint LangGraph do thread (phone:agent_id) do atendimento.

    Útil quando o agente "decora" um pattern errado das últimas mensagens
    (ex: respondeu "não tenho info" sem chamar tool, e modelo passa a
    replicar). Limpar força próxima mensagem a começar do zero com prompt
    + tools atuais.

    Não toca em message_queue, conversations, langgraph.store nem
    cliente_memoria. Só admin da empresa pode executar.
    """
    pool = await get_pool()

    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Só admin pode resetar conversa.",
        )

    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")

    cliente = await get_cliente_by_id(pool, atd.cliente_id)
    if cliente is None or cliente.empresa_id != empresa_id:
        raise HTTPException(
            status_code=404, detail="Cliente do atendimento não encontrado."
        )

    rows_deleted = await reset_thread_checkpoint(
        pool, cliente.telefone, atd.agente_atual
    )

    logger.info(
        "thread_checkpoint_reset",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        actor_user_id=user_id,
        phone=cliente.telefone,
        agent_id=atd.agente_atual,
        rows_deleted=rows_deleted,
    )
    return {
        "ok": True,
        "rows_deleted": rows_deleted,
        "thread_id": f"{cliente.telefone}:{atd.agente_atual}",
    }


@router.post("/{atendimento_id}/mensagens/{message_id}/reprocessar")
async def reprocessar_mensagem(
    atendimento_id: int,
    message_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.reprocessar")),
) -> dict:
    """Devolve à fila uma mensagem que a IA pulou ou que falhou.

    Casos cobertos: `status='failed'`, `[modo manual` e `[whitelist`.
    `[handoff humano` fica de fora — ali um atendente assumiu, e a IA
    responder por cima seria pior que o problema.

    Revalida os gates ANTES de reenfileirar. O botão aparecer não basta: a
    condição pode continuar valendo, e sem estas checagens a mensagem voltaria
    pra fila só pra ser pulada de novo, gastando token e confundindo o
    operador. Cada recusa diz o que fazer.

    Envia WhatsApp real ao cliente e consome tokens.
    """
    pool = await get_pool()
    atd = await _load_atendimento_in_empresa(atendimento_id, empresa_id)

    # Handoff: humano no controle. Vale pro atendimento inteiro, não só pra
    # mensagem — por isso checa aqui e não pelo marker.
    if atd.status == "em_andamento" and atd.assigned_to_user_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Atendimento está com um atendente humano. "
                "Reprocessar faria a IA responder por cima dele."
            ),
        )

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT phone_number, status, response, conexao_id "
            "FROM message_queue WHERE id = %s AND empresa_id = %s "
            "AND atendimento_id = %s",
            (message_id, empresa_id, atendimento_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

    phone, status, response, conexao_id = row

    elegivel = status == "failed" or any(
        (response or "").startswith(m) for m in MARKERS_REPROCESSAVEIS
    )
    if not elegivel:
        raise HTTPException(
            status_code=409,
            detail="Essa mensagem já foi respondida ou não pode ser reprocessada.",
        )

    # Gates que continuam valendo → reprocessar só repetiria o skip.
    if conexao_id is not None:
        conexao = await get_conexao_by_id(pool, conexao_id)
        if conexao is not None and conexao.tipo_atendimento == "manual":
            raise HTTPException(
                status_code=409,
                detail=(
                    "A conexão está em modo manual. "
                    "Ligue a IA na conexão antes de reprocessar."
                ),
            )

    if await is_whitelisted(pool, empresa_id, phone):
        raise HTTPException(
            status_code=409,
            detail=(
                "Esse número está na lista de bloqueio da IA. "
                "Remova-o da whitelist antes de reprocessar."
            ),
        )

    # Corrida entre dois operadores: quem chegar depois não reenfileira de
    # novo — evita o cliente receber a mesma resposta duas vezes.
    if not await reenfileirar_mensagem(pool, empresa_id, atendimento_id, message_id):
        raise HTTPException(
            status_code=409,
            detail="Mensagem já foi reprocessada por outra pessoa.",
        )

    logger.info(
        "mensagem_reprocessada_manual",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        message_id=message_id,
        actor_user_id=user_id,
    )
    return {"ok": True, "message_id": message_id}


@router.get("/{atendimento_id}/tags")
async def list_tags_endpoint(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista tags aplicadas no atendimento + quem aplicou (humano/IA)."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    items = await list_tags_de_atendimento(
        pool, atendimento_id=atendimento_id, empresa_id=empresa_id
    )
    return {"items": items}


@router.post("/{atendimento_id}/tags")
async def apply_tags(
    atendimento_id: int,
    payload: ApplyTagsInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.tag.aplicar")),
) -> dict:
    """Aplica delta de tags (add/remove) num atendimento.

    Idempotente. Cada linha inserida em `atendimento_tag` registra
    `aplicado_por_user_id` pra audit. Tags de outras empresas são
    silenciosamente filtradas no INSERT (JOIN com `tag.empresa_id`).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    result = await apply_tags_to_atendimento(
        pool,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        add_tag_ids=payload.add,
        remove_tag_ids=payload.remove,
        aplicado_por_user_id=user_id,
        aplicado_por_ia=False,
    )
    return result


@router.post("/{atendimento_id}/nota")
async def criar_nota_interna_endpoint(
    atendimento_id: int,
    payload: NotaInternaInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.nota_interna.criar")),
) -> dict:
    """Cria nota interna na timeline do atendimento.

    A nota fica em message_queue com `interna=true` — aparece em
    GET /mensagens normalmente, mas worker NUNCA envia outbound
    (gate em shared/outbound.py + nunca enfileirada como queued).
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    return await create_nota_interna(
        pool,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        user_id=user_id,
        texto=payload.texto.strip(),
    )


@router.post("/{atendimento_id}/marcar-lido")
async def marcar_lido_endpoint(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """UPSERT em atendimento_visualizacao (mig 052) — zera badge "nova".

    Sem perm explícita: qualquer user que pode ver o atendimento pode
    marcar como lido pra si próprio.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    await marcar_lido(pool, atendimento_id=atendimento_id, user_id=user_id)
    return {"ok": True}


@router.post("/{atendimento_id}/marcar-nao-lido")
async def marcar_nao_lido_endpoint(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Inverso do marcar-lido — apaga o read receipt deste user (leva fila).

    A conversa volta a contar como não lida pra ELE (abrir por engano não
    queima mais o marcador de "voltar aqui"). Mesma superfície de auth do
    marcar-lido: efeito restrito ao próprio usuário.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    await marcar_nao_lido(pool, atendimento_id=atendimento_id, user_id=user_id)
    return {"ok": True}


# ---- Cleanup de atendimentos zumbis (manual via UI) ----


@router.get("/cleanup-zumbis/preview")
async def cleanup_zumbis_preview_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> dict:
    """Conta atendimentos zumbis (preview, não modifica)."""
    pool = await get_pool()
    return await preview_zumbis(pool, empresa_id)


@router.post("/cleanup-zumbis")
async def cleanup_zumbis_endpoint(
    dry_run: bool = Query(default=False),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.write")),
) -> dict:
    """Executa cleanup manual de atendimentos zumbis.

    Fecha como `abandonado` atendimentos:
    - `aguardando` > N dias (config empresa, default 2)
    - `em_andamento` sem msg há > M dias (config empresa, default 1)

    `dry_run=true` retorna preview sem modificar.
    """
    pool = await get_pool()
    return await cleanup_zumbis(
        pool,
        empresa_id,
        dry_run=dry_run,
        motivo=f"cleanup_manual:{user_id}",
    )
