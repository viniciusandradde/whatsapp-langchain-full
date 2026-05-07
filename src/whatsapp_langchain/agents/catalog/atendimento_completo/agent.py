"""Agente Atendimento Completo — multimodal pra atendimento ao cliente.

Espelha vsa_tech (mesma assinatura `build_graph`, mesmo padrão `create_agent`)
mas adiciona 4 tools multimodais SEMPRE habilitadas:
- analyze_image (re-analise imagem com pergunta direcionada)
- transcribe_audio (re-transcrição literal)
- extract_document (PDF/DOCX → texto, com OCR fallback)
- summarize_document (resumo executivo + focus opcional)

Pré-processamento automático do worker (descrição/transcrição inicial)
continua igual; tools são pra REFINAR quando o agente precisar de detalhe
específico não capturado na primeira passada.
"""

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.middleware import get_context_middleware
from whatsapp_langchain.agents.tools import (
    add_cliente_tag,
    analyze_image,
    calendar_cancel_event,
    calendar_create_event,
    calendar_find_free_slots,
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_list_events,
    calendar_reschedule_event,
    calendar_set_active_calendar,
    classificar_atendimento,
    close_atendimento,
    create_cliente_anotacao,
    extract_document,
    get_cliente_anotacoes,
    get_cliente_history,
    get_cliente_profile,
    read_cliente_memoria,
    read_memory,
    save_cliente_fato,
    save_memory,
    search_knowledge_base,
    summarize_document,
    transcribe_audio,
    transfer_to_human,
    update_cliente,
)
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,
    pool: AsyncConnectionPool | None = None,  # noqa: ARG001
    empresa_id: int | None = None,  # noqa: ARG001
    calendar_enabled: bool = False,
    knowledge_enabled: bool = False,
    system_prompt_override: str | None = None,
    temperatura: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
):
    """Constrói o agente Atendimento Completo (multimodal)."""
    model = create_chat_model(
        model=chat_model,
        temperature=temperatura,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    middleware = get_context_middleware()

    tools: list = [save_memory, read_memory] if store else []

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
    if knowledge_enabled:
        tools.append(search_knowledge_base)

    # Tools CRM/atendimento — sempre habilitadas
    tools.extend(
        [
            get_cliente_profile,
            get_cliente_history,
            get_cliente_anotacoes,
            create_cliente_anotacao,
            add_cliente_tag,
            update_cliente,
            close_atendimento,
            classificar_atendimento,
            transfer_to_human,
        ]
    )

    # Tools memória estruturada por cliente — sempre habilitadas
    tools.extend([read_cliente_memoria, save_cliente_fato])

    # ---- Diferencial Atendimento Completo: 4 tools multimodais ----
    # SEMPRE habilitadas (independem de flags). Agente usa pra refinar
    # análise da mídia que o pré-processamento automático já entregou.
    tools.extend(
        [
            analyze_image,
            transcribe_audio,
            extract_document,
            summarize_document,
        ]
    )

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
