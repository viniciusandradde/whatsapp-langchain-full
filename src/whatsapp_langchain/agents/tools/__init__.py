"""Ferramentas reutilizáveis para agentes LangGraph."""

from whatsapp_langchain.agents.tools.calendar import (
    calendar_cancel_event,
    calendar_create_event,
    calendar_find_free_slots,
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_list_events,
    calendar_reschedule_event,
    calendar_set_active_calendar,
)
from whatsapp_langchain.agents.tools.cliente_atendimento import (
    add_cliente_tag,
    close_atendimento,
    create_cliente_anotacao,
    get_cliente_anotacoes,
    get_cliente_history,
    get_cliente_profile,
    transfer_to_human,
    update_cliente,
)
from whatsapp_langchain.agents.tools.cliente_memoria import (
    read_cliente_memoria,
    save_cliente_fato,
)
from whatsapp_langchain.agents.tools.knowledge import search_knowledge_base
from whatsapp_langchain.agents.tools.memory import read_memory, save_memory
from whatsapp_langchain.agents.tools.midia import (
    analyze_image,
    extract_document,
    summarize_document,
    transcribe_audio,
)

__all__ = [
    "add_cliente_tag",
    "analyze_image",
    "calendar_cancel_event",
    "calendar_create_event",
    "calendar_find_free_slots",
    "calendar_get_current_time",
    "calendar_list_calendars",
    "calendar_list_events",
    "calendar_reschedule_event",
    "calendar_set_active_calendar",
    "close_atendimento",
    "create_cliente_anotacao",
    "extract_document",
    "get_cliente_anotacoes",
    "get_cliente_history",
    "get_cliente_profile",
    "read_cliente_memoria",
    "read_memory",
    "save_cliente_fato",
    "save_memory",
    "search_knowledge_base",
    "summarize_document",
    "transcribe_audio",
    "transfer_to_human",
    "update_cliente",
]
