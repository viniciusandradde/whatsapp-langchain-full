"""Webhook síncrono — endpoint educacional para testes rápidos.

Diferente do webhook Twilio (assíncrono via fila), este endpoint processa
a mensagem inline e retorna a resposta diretamente. Útil para:
- Testes rápidos sem Worker rodando
- Entender o fluxo sem a complexidade da fila
- Demonstrações e debugging

NÃO usar em produção — não tem debounce, fila, retry ou rate limit.

Uso:
    curl -X POST "http://localhost:8000/webhook/sync?agent=rhawk_assistant" \
         -H "Content-Type: application/json" \
         -d '{"phone": "+5511999999999", "message": "Olá!"}'
"""

import structlog
from fastapi import APIRouter, Query
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field

from whatsapp_langchain.agents.loader import load_graph
from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()

router = APIRouter(tags=["webhook"])


class SyncRequest(BaseModel):
    """Payload do webhook síncrono."""

    phone: str = Field(description="Número do remetente (E.164)")
    message: str = Field(description="Texto da mensagem")


class SyncResponse(BaseModel):
    """Resposta do webhook síncrono."""

    response: str = Field(description="Resposta do agente")
    agent_id: str


@router.post("/webhook/sync", response_model=SyncResponse)
async def webhook_sync(
    payload: SyncRequest,
    agent: str = Query(description="ID do agente"),
) -> SyncResponse:
    """Processa mensagem de forma síncrona (sem fila).

    Carrega o agente, executa com a mensagem, e retorna a resposta
    diretamente. Sem checkpointer — cada chamada é independente.

    Args:
        payload: Mensagem a processar.
        agent: ID do agente (query param).

    Returns:
        Resposta do agente.
    """
    logger.info(
        "webhook_sync_received",
        phone=payload.phone,
        agent_id=agent,
    )

    # Store só é criado se memória está habilitada
    # InMemoryStore em dev: sem persistência entre requests,
    # mas funcional para testar o fluxo de save/recall dentro de uma chamada
    store = InMemoryStore() if settings.memory_enabled else None

    # Carrega agente sem checkpointer (sem persistência)
    graph = load_graph(agent, store=store)

    # Executa o agente
    thread_id = f"{payload.phone}:{agent}"
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": payload.message}]},
        config={
            "configurable": {
                "thread_id": thread_id,
                "user_id": payload.phone,
            }
        },
    )

    # Extrai a resposta da última mensagem
    response_text = result["messages"][-1].content

    logger.info(
        "webhook_sync_responded",
        phone=payload.phone,
        agent_id=agent,
    )

    return SyncResponse(response=response_text, agent_id=agent)
