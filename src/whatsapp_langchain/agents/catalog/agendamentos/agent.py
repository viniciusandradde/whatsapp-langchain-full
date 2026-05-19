"""Agente Agendamentos — integração Wareline ConecteHub.

Set enxuto de tools focado em marcar/remarcar/cancelar consultas.
Espelha contrato de `vsa_tech`/`atendimento_completo` (mesma assinatura
`build_graph`) pra ser carregado pelo loader padrão.
"""

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.middleware import get_context_middleware
from whatsapp_langchain.agents.tools import (
    classificar_atendimento,
    get_cliente_history,
    get_cliente_profile,
    read_memory,
    save_memory,
    transfer_to_human,
    wareline_buscar_paciente,
    wareline_consultar_agenda,
    wareline_criar_agendamento,
)
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,
    pool: AsyncConnectionPool | None = None,  # noqa: ARG001
    empresa_id: int | None = None,  # noqa: ARG001
    calendar_enabled: bool = False,  # noqa: ARG001 — Wareline substitui Google Calendar
    knowledge_enabled: bool = False,  # noqa: ARG001 — agente não usa KB
    system_prompt_override: str | None = None,
    temperatura: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
):
    """Constrói o agente Agendamentos.

    Tools (~8 total):
    - Wareline (3): buscar_paciente, consultar_agenda, criar_agendamento
    - CRM contexto (2): get_cliente_profile, get_cliente_history
    - Memória (2, se store): save_memory, read_memory
    - Escalação (2): transfer_to_human, classificar_atendimento
    """
    model = create_chat_model(
        model=chat_model,
        temperature=temperatura,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    middleware = get_context_middleware()

    tools: list = [save_memory, read_memory] if store else []

    # Wareline tools — sempre habilitadas neste template
    tools.extend(
        [
            wareline_buscar_paciente,
            wareline_consultar_agenda,
            wareline_criar_agendamento,
        ]
    )

    # Contexto CRM básico (saber quem é o cliente + histórico no Nexus)
    tools.extend(
        [
            get_cliente_profile,
            get_cliente_history,
        ]
    )

    # Escalação + classificação omnichannel
    tools.extend(
        [
            classificar_atendimento,
            transfer_to_human,
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
