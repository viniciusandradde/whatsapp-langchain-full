"""CRUD de Atendimentos do painel admin (M3 CRM Light).

A lista é paginada por **tipo de visualização** (`meus`, `aguardando`,
`grupos`, `outros`) — derivado em runtime, sem coluna no banco. As
mutações (`claim`, `close`, `transfer`) seguem o ciclo de vida descrito
em `shared/atendimento.py`.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.atendimento import (
    claim_atendimento,
    close_atendimento,
    get_atendimento_by_id,
    list_atendimento_mensagens,
    list_atendimentos,
    transfer_atendimento,
)
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_admin_of
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
from whatsapp_langchain.shared.models import Atendimento
from whatsapp_langchain.shared.outbound import OutboundError, send_outbound_manual
from whatsapp_langchain.shared.queue import reset_thread_checkpoint
from whatsapp_langchain.shared.variavel import build_render_context, render_template

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/atendimentos",
    tags=["atendimentos"],
    dependencies=[Depends(verify_service_token)],
)


TipoVisualizacao = Literal["meus", "aguardando", "grupos", "outros"]


class CloseInput(BaseModel):
    status: Literal["resolvido", "abandonado"] = "resolvido"


class TransferInput(BaseModel):
    user_id: str


class ResponderInput(BaseModel):
    conteudo: str


@router.get("")
async def list_my_atendimentos(
    tipo: TipoVisualizacao = Query(default="aguardando"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[Atendimento]]:
    """Lista atendimentos da empresa filtrados pelo tipo (4 abas)."""
    pool = await get_pool()
    rows = await list_atendimentos(
        pool,
        empresa_id,
        tipo=tipo,
        current_user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return {"atendimentos": rows}


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


@router.get("/{atendimento_id}")
async def read_atendimento(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Atendimento:
    """Detalhe — inclui cliente_nome/cliente_telefone via JOIN."""
    return await _load_atendimento_in_empresa(atendimento_id, empresa_id)


# ---- E2.E SSE ----


@router.get("/{atendimento_id}/events")
async def sse_events(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
):
    """Stream de eventos do atendimento via SSE (E2.E).

    Substitui o polling 3s do AtendimentoDrawer. Backend ouve canal
    Postgres `atendimento_event` (alimentado por triggers da mig 035) e
    relay eventos cujo `atendimento_id` bate com o requested.

    Conexão dedicada (psycopg async standalone), fora do pool — LISTEN
    bloqueia a conexão pra outros usos. Heartbeat a cada 25s pra
    sobreviver ao Traefik (idle timeout default 60s).

    Frontend acessa via Next.js API route proxy (/api/sse/...) que
    adiciona Authorization + X-User-Id headers — EventSource nativo
    não suporta headers custom.
    """
    import asyncio
    import json

    import psycopg
    from fastapi.responses import StreamingResponse

    from whatsapp_langchain.shared.config import settings

    # Valida ANTES de abrir o stream (retorna 4xx imediato se acesso negado)
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)

    async def event_generator():
        try:
            async with await psycopg.AsyncConnection.connect(
                settings.database_url, autocommit=True
            ) as conn:
                await conn.execute("LISTEN atendimento_event")
                yield (
                    f"event: connected\n"
                    f"data: {json.dumps({'atendimento_id': atendimento_id})}\n\n"
                )

                # psycopg.notifies(timeout=N) retorna AsyncGenerator que
                # *termina* quando o timeout expira. Loop externo re-abre
                # o generator + emite heartbeat a cada ciclo (25s).
                while True:
                    async for notify in conn.notifies(timeout=25):
                        try:
                            payload = json.loads(notify.payload)
                        except (ValueError, TypeError):
                            continue
                        if payload.get("atendimento_id") != atendimento_id:
                            continue
                        evt_name = payload.get("event", "update")
                        yield f"event: {evt_name}\ndata: {notify.payload}\n\n"
                    yield ": heartbeat\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sse_atendimento_failed",
                atendimento_id=atendimento_id,
                error=str(exc),
            )
            yield (
                f"event: error\n"
                f"data: {json.dumps({'error': str(exc)[:200]})}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{atendimento_id}/mensagens")
async def read_atendimento_mensagens(
    atendimento_id: int,
    limit: int = Query(default=200, ge=1, le=500),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Mensagens cronológicas do atendimento (ASC).

    Cobre só mensagens com `atendimento_id` preenchido — inbound antigas
    (anteriores ao M3) ficam fora; o histórico legado segue acessível
    pela rota `/api/chats/{phone}` se for preciso.
    """
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    mensagens = await list_atendimento_mensagens(
        pool, atendimento_id, empresa_id, limit=limit
    )
    return {"atendimento_id": atendimento_id, "mensagens": mensagens}


@router.post("/{atendimento_id}/claim")
async def claim(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Atendimento:
    """Operador "puxa" o atendimento — vira em_andamento + assigned=user."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
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
    # Sprint E.3 — Mensagem auto ao cliente avisando que atendente assumiu
    # ("Você foi transferido para o atendente *X*"). Best-effort: erro
    # não bloqueia claim. Resolve nome via auth.user; fallback "atendente".
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
            conteudo=(
                f"Você foi transferido para o atendente *{nome_atendente}*."
            ),
            tag_user_id=f"system:claim:{user_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "claim_outbound_failed",
            atendimento_id=atendimento_id,
            error=str(exc),
        )
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


@router.post("/{atendimento_id}/close")
async def close(
    atendimento_id: int,
    body: CloseInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
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
    return out


@router.post("/{atendimento_id}/responder")
async def responder(
    atendimento_id: int,
    body: ResponderInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Envia mensagem manual do operador via Twilio (M4.a).

    O atendimento precisa estar `aguardando` ou `em_andamento`. A mensagem
    é persistida em message_queue como row outbound-only — aparece na
    timeline do drawer junto às mensagens do agente IA.

    Antes do envio, `{{empresa.*}}`, `{{cliente.*}}`, `{{data.*}}` e
    `{{var.*}}` são resolvidos server-side (M5.d) — operador pode digitar
    `Olá {{cliente.nome}}!` direto e o cliente recebe o texto final.
    """
    pool = await get_pool()
    ctx = await build_render_context(
        pool, empresa_id, atendimento_id=atendimento_id
    )
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


@router.post("/{atendimento_id}/transfer")
async def transfer(
    atendimento_id: int,
    body: TransferInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Atendimento:
    """Transfere a um operador (mantém em_andamento, troca assigned)."""
    await _load_atendimento_in_empresa(atendimento_id, empresa_id)
    pool = await get_pool()
    out = await transfer_atendimento(pool, atendimento_id, body.user_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    logger.info(
        "atendimento_transferred",
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        from_user=user_id,
        to_user=body.user_id,
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
            "departamento_nome": None,  # endpoint manual não resolve nome — caller pode resolver
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
