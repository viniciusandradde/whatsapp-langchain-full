"""Rotas administrativas para o painel de controle.

Endpoints para visualizar conversas, métricas e agentes disponíveis.
Usado pelo frontend (Next.js Admin Panel).

Uso:
    curl http://localhost:8000/api/agents
    curl http://localhost:8000/api/chats?limit=20
    curl http://localhost:8000/api/chats/+5511999999999
    curl http://localhost:8000/api/metrics
"""

import importlib

import structlog
from fastapi import APIRouter, Depends, Query

from whatsapp_langchain.agents.loader import AgentNotFoundError, list_agents
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.agente_ia import (
    delete_agente_ia_config,
    get_agente_ia_config,
    upsert_agente_ia_config,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import list_empresas_of_user
from whatsapp_langchain.shared.llm import CURATED_MODELS
from whatsapp_langchain.shared.models import (
    AgenteIAConfig,
    AgenteIAConfigInput,
    AgentLLMConfigResponse,
    Empresa,
    ModelInfo,
    UpdateAgentLLMConfigRequest,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["admin"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("/agents")
async def get_agents() -> dict[str, list[str]]:
    """Lista agentes disponíveis no catálogo.

    Returns:
        Lista de agent_ids registrados.
    """
    return {"agents": list_agents()}


@router.get("/models")
async def list_models() -> dict[str, list[ModelInfo]]:
    """Lista curada de modelos LLM disponíveis no painel.

    Tipo "chat" são os modelos principais; "media" são os usados pelo
    pré-processamento multimodal (imagem/áudio).
    """
    return {"models": [ModelInfo(**m) for m in CURATED_MODELS]}


@router.get("/empresas")
async def list_my_empresas(
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[Empresa]]:
    """Lista todas as empresas onde o usuário (Better Auth) é membro.

    Usado pelo `<EmpresaSwitcher>` do frontend pra montar o dropdown.
    Usuários sem nenhuma empresa retornam lista vazia (sem 403 — o painel
    decide o que mostrar).
    """
    pool = await get_pool()
    return {"empresas": await list_empresas_of_user(pool, user_id)}


@router.get("/agents/{agent_id}/config")
async def get_agent_config(
    agent_id: str,
    empresa_id: int = Depends(get_empresa_context),
) -> AgentLLMConfigResponse:
    """Retorna a configuração de modelos resolvida (DB ou env) + overrides crus."""
    if agent_id not in list_agents():
        raise AgentNotFoundError(agent_id)

    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT chat_model, midia_model FROM agent_llm_config
             WHERE empresa_id = %s AND agent_id = %s
            """,
            (empresa_id, agent_id),
        )
        row = await cursor.fetchone()

    chat_override = row[0] if row else None
    midia_override = row[1] if row else None

    return AgentLLMConfigResponse(
        agent_id=agent_id,
        chat_model=chat_override or settings.openrouter_model,
        midia_model=midia_override or settings.openrouter_midia_model,
        chat_model_override=chat_override,
        midia_model_override=midia_override,
    )


@router.put("/agents/{agent_id}/config")
async def update_agent_config(
    agent_id: str,
    body: UpdateAgentLLMConfigRequest,
    empresa_id: int = Depends(get_empresa_context),
) -> AgentLLMConfigResponse:
    """Atualiza overrides de modelo. None ou string vazia limpa o override."""
    if agent_id not in list_agents():
        raise AgentNotFoundError(agent_id)

    chat = (body.chat_model or "").strip() or None
    midia = (body.midia_model or "").strip() or None

    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO agent_llm_config (empresa_id, agent_id, chat_model, midia_model)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (empresa_id, agent_id) DO UPDATE SET
                chat_model = EXCLUDED.chat_model,
                midia_model = EXCLUDED.midia_model,
                updated_at = NOW()
            """,
            (empresa_id, agent_id, chat, midia),
        )

    logger.info(
        "agent_llm_config_updated",
        empresa_id=empresa_id,
        agent_id=agent_id,
        chat=chat,
        midia=midia,
    )

    return await get_agent_config(agent_id, empresa_id=empresa_id)


# --- M5.b AgenteIA configurável: prompt + temperatura ---


def _load_default_system_prompt(agent_id: str) -> str:
    """Lê SYSTEM_PROMPT do módulo do catálogo (placeholder pra UI)."""
    try:
        prompts_mod = importlib.import_module(
            f"whatsapp_langchain.agents.catalog.{agent_id}.prompts"
        )
        return getattr(prompts_mod, "SYSTEM_PROMPT", "")
    except ModuleNotFoundError:
        return ""


@router.get("/agents/{agent_id}/agente-ia-config")
async def get_agente_ia_config_route(
    agent_id: str,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Retorna o override (se existir) + o prompt default do catálogo."""
    if agent_id not in list_agents():
        raise AgentNotFoundError(agent_id)
    pool = await get_pool()
    config = await get_agente_ia_config(pool, empresa_id, agent_id)
    return {
        "config": config.model_dump(mode="json") if config else None,
        "default_system_prompt": _load_default_system_prompt(agent_id),
    }


@router.put("/agents/{agent_id}/agente-ia-config")
async def update_agente_ia_config_route(
    agent_id: str,
    body: AgenteIAConfigInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> AgenteIAConfig:
    if agent_id not in list_agents():
        raise AgentNotFoundError(agent_id)
    pool = await get_pool()
    out = await upsert_agente_ia_config(
        pool, empresa_id, agent_id, body, user_id=user_id
    )
    logger.info(
        "agente_ia_config_updated",
        empresa_id=empresa_id,
        agent_id=agent_id,
        ativo=out.ativo,
        has_prompt=bool(out.system_prompt_override),
        temperatura=out.temperatura,
        user_id=user_id,
    )
    return out


@router.delete("/agents/{agent_id}/agente-ia-config", status_code=204)
async def delete_agente_ia_config_route(
    agent_id: str,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    if agent_id not in list_agents():
        raise AgentNotFoundError(agent_id)
    pool = await get_pool()
    deleted = await delete_agente_ia_config(pool, empresa_id, agent_id)
    logger.info(
        "agente_ia_config_deleted",
        empresa_id=empresa_id,
        agent_id=agent_id,
        deleted=deleted,
        user_id=user_id,
    )


@router.get("/chats")
async def get_chats(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista conversas ativas da empresa ativa, ordenadas por última mensagem.

    Args:
        limit: Máximo de resultados (1-100). Default: 20.
        offset: Offset para paginação. Default: 0.

    Returns:
        Lista de conversas com paginação.
    """
    pool = await get_pool()

    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT phone_number, agent_id, thread_id, last_message,
                   last_message_at, message_count, created_at
            FROM conversations
             WHERE empresa_id = %s
            ORDER BY last_message_at DESC
            LIMIT %s OFFSET %s
            """,
            (empresa_id, limit, offset),
        )
        rows = await cursor.fetchall()

        count_cursor = await conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE empresa_id = %s",
            (empresa_id,),
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

    chats = [
        {
            "phone_number": row[0],
            "agent_id": row[1],
            "thread_id": row[2],
            "last_message": row[3],
            "last_message_at": row[4].isoformat() if row[4] else None,
            "message_count": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
        }
        for row in rows
    ]

    return {"chats": chats, "total": total, "limit": limit, "offset": offset}


@router.get("/chats/{phone_number:path}")
async def get_chat_messages(
    phone_number: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista mensagens de uma conversa específica (na empresa ativa)."""
    pool = await get_pool()

    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, agent_id, incoming_message, media_type,
                   normalized_input, media_processing_status,
                   response, status, created_at, processed_at,
                   media_processing_error, error
            FROM message_queue
            WHERE empresa_id = %s AND phone_number = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (empresa_id, phone_number, limit, offset),
        )
        rows = await cursor.fetchall()

    messages = [
        {
            "id": row[0],
            "agent_id": row[1],
            "incoming_message": row[2],
            "media_type": row[3],
            "normalized_input": row[4],
            "media_processing_status": row[5],
            "response": row[6],
            "status": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "processed_at": row[9].isoformat() if row[9] else None,
            "media_processing_error": row[10],
            "error": row[11],
        }
        for row in rows
    ]

    return {"phone_number": phone_number, "messages": messages}


@router.get("/metrics")
async def get_metrics(
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Métricas operacionais da fila — escopadas pela empresa ativa."""
    pool = await get_pool()

    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT COUNT(*) FROM message_queue
             WHERE empresa_id = %s AND created_at >= CURRENT_DATE
            """,
            (empresa_id,),
        )
        row = await cursor.fetchone()
        total_today = row[0] if row else 0

        cursor = await conn.execute(
            """
            SELECT COUNT(*) FROM message_queue
             WHERE empresa_id = %s
               AND status = 'failed'
               AND created_at >= CURRENT_DATE
            """,
            (empresa_id,),
        )
        row = await cursor.fetchone()
        failures_today = row[0] if row else 0

        cursor = await conn.execute(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (processed_at - created_at)))
              FROM message_queue
             WHERE empresa_id = %s
               AND status = 'done'
               AND processed_at IS NOT NULL
               AND created_at >= CURRENT_DATE
            """,
            (empresa_id,),
        )
        row = await cursor.fetchone()
        avg_processing_time = (
            float(round(row[0], 2)) if row and row[0] is not None else None
        )

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM message_queue"
            " WHERE empresa_id = %s AND status = 'queued'",
            (empresa_id,),
        )
        row = await cursor.fetchone()
        queue_size = row[0] if row else 0

    return {
        "total_today": total_today,
        "failures_today": failures_today,
        "avg_processing_time_seconds": avg_processing_time,
        "queue_size": queue_size,
    }


@router.get("/queue")
async def get_queue(
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Visão da fila — contadores e últimas 50 mensagens da empresa ativa."""
    pool = await get_pool()

    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT status, COUNT(*) as count
              FROM message_queue
             WHERE empresa_id = %s AND created_at >= CURRENT_DATE
             GROUP BY status
            """,
            (empresa_id,),
        )
        status_rows = await cursor.fetchall()

        counters = {"queued": 0, "processing": 0, "done": 0, "failed": 0}
        for row in status_rows:
            counters[row[0]] = row[1]

        cursor = await conn.execute(
            """
            SELECT id, phone_number, agent_id,
                   LEFT(incoming_message, 100) as incoming_message,
                   status, created_at, attempts, error
              FROM message_queue
             WHERE empresa_id = %s
             ORDER BY created_at DESC
             LIMIT 50
            """,
            (empresa_id,),
        )
        message_rows = await cursor.fetchall()

    messages = [
        {
            "id": row[0],
            "phone_number": row[1],
            "agent_id": row[2],
            "incoming_message": row[3],
            "status": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "attempts": row[6],
            "error": row[7],
        }
        for row in message_rows
    ]

    logger.debug(
        "queue_status_fetched", counters=counters, messages_count=len(messages)
    )

    return {"counters": counters, "messages": messages}
