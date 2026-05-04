"""Agente vsa_tech - assistente da VSA Tech.

Agente simples usando create_agent do LangChain 1.0.
Usa middleware de contexto configurável (trim ou summarize)
e memória semântica cross-thread via LangGraph Store.

Este arquivo contém a factory `build_graph()`. Para langgraph dev,
veja graph.py que exporta a variável `graph`.

Configuração via .env:
    OPENROUTER_API_KEY=sk-or-...       # API key do OpenRouter
    OPENROUTER_MODEL=anthropic/...     # Modelo principal
    CONTEXT_STRATEGY=trim              # trim | summarize | none
    TRIM_KEEP_TURNS=5                  # Turnos a manter (trim)
    SUMMARIZE_TRIGGER_TOKENS=4000      # Tokens antes de sumarizar
    SUMMARIZE_KEEP_MESSAGES=10         # Mensagens após sumarização
    SUMMARIZE_MODEL=anthropic/...      # Modelo para sumarização
    MEMORY_ENABLED=true                # Habilita memória semântica
"""

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.middleware import get_context_middleware
from whatsapp_langchain.agents.tools import (
    add_cliente_tag,
    calendar_cancel_event,
    calendar_create_event,
    calendar_find_free_slots,
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_list_events,
    calendar_reschedule_event,
    calendar_set_active_calendar,
    close_atendimento,
    create_cliente_anotacao,
    get_cliente_anotacoes,
    get_cliente_history,
    get_cliente_profile,
    read_cliente_memoria,
    read_memory,
    save_cliente_fato,
    save_memory,
    search_knowledge_base,
    transfer_to_human,
    update_cliente,
)
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,
    pool: AsyncConnectionPool | None = None,  # noqa: ARG001 — reservado pra futuras tools sync
    empresa_id: int | None = None,  # noqa: ARG001 — idem
    calendar_enabled: bool = False,
    knowledge_enabled: bool = False,
    system_prompt_override: str | None = None,
    temperatura: float | None = None,
):
    """Constrói o agente vsa_tech.

    O agente usa middleware de contexto configurável via CONTEXT_STRATEGY:
    - trim: Remove mensagens antigas (custo zero, perde contexto)
    - summarize: Sumariza mensagens antigas (custo extra, preserva contexto)
    - none: Sem gerenciamento de contexto

    Se store for fornecido, habilita memória semântica:
    - Recall automático via middleware (busca memórias antes de cada chamada)
    - Save explícito via tool save_memory (agente decide quando salvar)

    Args:
        checkpointer: Checkpointer para persistência de estado.
                      None em dev (in-memory), PostgresSaver em prod.
        store: Store para memória semântica cross-thread.
               None desabilita memória, InMemoryStore em dev,
               AsyncPostgresStore em prod.
        chat_model: Override do modelo principal (ex: "openai/gpt-4o-mini").
                    None = usa settings.openrouter_model do .env.

    Returns:
        CompiledStateGraph: Agente compilado pronto para uso.
    """
    # Modelo principal com rate limiter centralizado (shared/llm.py).
    # chat_model=None faz fallback pra settings.openrouter_model.
    # temperatura=None deixa o provider aplicar o default dele.
    model = create_chat_model(model=chat_model, temperature=temperatura)

    # Middleware de contexto baseado em CONTEXT_STRATEGY
    middleware = get_context_middleware()

    # Tools de memória — só disponibiliza quando store existe.
    tools: list = [save_memory, read_memory] if store else []
    # Tools de Google Calendar — só quando a empresa tem config ativo
    # (loader.py decide via DB e passa `calendar_enabled=True`).
    if calendar_enabled:
        tools.extend(
            [
                calendar_get_current_time,
                calendar_list_calendars,
                calendar_set_active_calendar,
                calendar_list_events,
                calendar_find_free_slots,
                calendar_create_event,
                calendar_reschedule_event,
                calendar_cancel_event,
            ]
        )
    # Tool de RAG — só quando a empresa tem ≥1 documento ativo
    # (loader.py decide via DB e passa `knowledge_enabled=True`).
    if knowledge_enabled:
        tools.append(search_knowledge_base)

    # Tools de cliente/atendimento (M5.b.1) — sempre habilitadas porque
    # M3 já criou as tabelas pra todas as empresas. As tools validam
    # empresa_id no runtime pra anti-tenant escape.
    tools.extend(
        [
            get_cliente_profile,
            get_cliente_history,
            get_cliente_anotacoes,
            create_cliente_anotacao,
            add_cliente_tag,
            update_cliente,
            close_atendimento,
            transfer_to_human,
        ]
    )

    # Tools de memória estruturada por cliente (M5.b.2) — sempre habilitadas
    # via tabela cliente_memoria (M5.b.2). Anti-tenant escape via empresa_id
    # check na tool.
    tools.extend([read_cliente_memoria, save_cliente_fato])

    # Override do prompt vem do `agente_ia_config` da empresa via loader.
    # Vazio/None = usa o template hardcoded (`SYSTEM_PROMPT`).
    effective_prompt = (
        system_prompt_override
        if system_prompt_override and system_prompt_override.strip()
        else SYSTEM_PROMPT
    )

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=effective_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
        store=store,
    )
