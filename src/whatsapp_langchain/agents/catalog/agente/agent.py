"""Topologia simples — o agente que conversa e usa as ferramentas marcadas.

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
from whatsapp_langchain.agents.tools import read_memory, save_memory
from whatsapp_langchain.agents.tools.cliente_atendimento import classificar_lead
from whatsapp_langchain.agents.tools.registry import resolve_tools
from whatsapp_langchain.shared.llm import create_chat_model

from .prompts import SYSTEM_PROMPT

# Só a descrição da tool não bastou: o agente de atendimento do dev respondeu
# a um "quero contratar o Pro esta semana" sem classificar (24/09/2026). O
# prompt de cada empresa não fala da tool, então o bloco entra quando ela está
# ligada. Texto FIXO no fim — não quebra o cache do prefixo do prompt.
INSTRUCAO_CLASSIFICAR_LEAD = """

<classificacao_do_lead>
Quando a conversa mostrar sinal comercial — perguntou preço ou condições,
pediu proposta ou orçamento, disse prazo ou urgência, fechou, ou desistiu —
chame a ferramenta `classificar_lead` em silêncio, junto com a sua resposta.
Não comente a classificação com o cliente. Conversa sem sinal comercial
(suporte, dúvida geral, saudação) não precisa de classificação.
</classificacao_do_lead>"""


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
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools_enabled: list[str] | None = None,
    aceita_imagem: bool = True,
    aceita_audio: bool = True,
    aceita_documento: bool = True,
    contexto_chars: int | None = None,
    trim_keep_turns: int | None = None,
):
    """Constrói o agente de topologia simples.

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
        contexto_chars: Teto de caracteres do histórico (ADR-004, tier
                        `agente_ia.contexto_tamanho` traduzido pelo loader).
                        None = sem teto (legado).
        trim_keep_turns: `agente_ia.janela_memoria` (mig 043). None = o
                         TRIM_KEEP_TURNS global. Até 2026-09 este campo era
                         salvo e ignorado — a UI prometia o que o worker
                         não fazia.

    Returns:
        CompiledStateGraph: Agente compilado pronto para uso.
    """
    # Modelo principal com rate limiter centralizado (shared/llm.py).
    # chat_model=None faz fallback pra settings.openrouter_model.
    # temperatura/top_p/max_tokens=None deixam o provider aplicar o default.
    model = create_chat_model(
        model=chat_model,
        temperature=temperatura,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    # Middleware de contexto baseado em CONTEXT_STRATEGY. Os dois limites do
    # agente (turnos e caracteres) só valem na estratégia "trim"; o menor
    # dos dois vence.
    middleware = get_context_middleware(
        trim_keep_turns=trim_keep_turns, trim_max_chars=contexto_chars
    )

    # Tools de memória semântica — dependem do store, não da config do agente.
    tools: list = [save_memory, read_memory] if store else []

    # Demais tools vêm do que o admin marcou em `agente_ia.tools_enabled`.
    # Até 2026-07-27 essa lista era hardcoded aqui e o campo do banco era
    # ignorado: os checkboxes do painel não faziam nada. O registry traduz
    # slug → tool e trata alias legado, backlog e fallback.
    #
    # `calendar_enabled`/`knowledge_enabled` continuam mandando: marcar o
    # slug não liga integração que a empresa não tem.
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

    # Override do prompt vem do `agente_ia_config` da empresa via loader.
    # Vazio/None = usa o template hardcoded (`SYSTEM_PROMPT`).
    effective_prompt = (
        system_prompt_override
        if system_prompt_override and system_prompt_override.strip()
        else SYSTEM_PROMPT
    )

    if classificar_lead in tools:
        effective_prompt += INSTRUCAO_CLASSIFICAR_LEAD

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=effective_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
        store=store,
    )
