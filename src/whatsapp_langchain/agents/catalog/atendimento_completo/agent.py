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
    knowledge_enabled: bool = False,
    system_prompt_override: str | None = None,
    temperatura: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools_enabled: list[str] | None = None,
    aceita_imagem: bool = True,
    aceita_audio: bool = True,
    aceita_documento: bool = True,
):
    """Constrói o agente Atendimento Completo (multimodal)."""
    model = create_chat_model(
        model=chat_model,
        temperature=temperatura,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    middleware = get_context_middleware()

    # Memória semântica é do runtime (depende do store), não da seleção do
    # admin — por isso fica fora do registry.
    tools: list = [save_memory, read_memory] if store else []

    # O resto vem do que está marcado no painel. Até a migration 154 esta
    # lista era CRAVADA aqui e `tools_enabled` era descartado: o admin
    # marcava caixa que não fazia nada. Ver docs/ANALISE-MODELO-AGENTE.md.
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
