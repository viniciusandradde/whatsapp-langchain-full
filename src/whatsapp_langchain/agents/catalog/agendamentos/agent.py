"""Agente Agendamentos — marcar, remarcar e cancelar consultas.

Usava a integração Wareline ConecteHub, removida em 2026-07-31 (decisão de
produto: integração externa passa a ser API + webhook genéricos). As tools
de agenda agora são as de Google Calendar, iguais às do `atendimento_completo`.
Espelha contrato de `vsa_tech`/`atendimento_completo` (mesma assinatura
`build_graph`) pra ser carregado pelo loader padrão.
"""

from langchain.agents import create_agent
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.middleware import get_context_middleware
from whatsapp_langchain.agents.tools import read_memory, save_memory
from whatsapp_langchain.agents.tools.registry import resolve_tools
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    chat_model: str | None = None,
    pool: AsyncConnectionPool | None = None,  # noqa: ARG001
    empresa_id: int | None = None,  # noqa: ARG001
    calendar_enabled: bool = False,
    knowledge_enabled: bool = False,  # noqa: ARG001 — agente não usa KB
    system_prompt_override: str | None = None,
    temperatura: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    # Aceito e ignorado: o loader passa pra TODO catalogo. Este agente
    # ainda monta as tools de forma fixa; sem o kwarg daria TypeError.
    tools_enabled: list[str] | None = None,
    aceita_imagem: bool = True,
    aceita_audio: bool = True,
    aceita_documento: bool = True,
):
    """Constrói o agente Agendamentos.

    Tools:
    - Agenda (8, se `calendar_enabled`): horário atual, listar agendas, definir
      agenda ativa, listar eventos, achar horário livre, criar, remarcar e
      cancelar
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

    # Ver atendimento_completo: a lista era cravada aqui e `tools_enabled`
    # descartado. Agora o painel manda. A migration 154 materializou o
    # conjunto que este template dava, pra ninguém perder comportamento.
    tools.extend(
        resolve_tools(
            tools_enabled,
            calendar_enabled=calendar_enabled,
            knowledge_enabled=knowledge_enabled,
            aceita_imagem=aceita_imagem,
            aceita_audio=aceita_audio,
            aceita_documento=aceita_documento,
        )
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
