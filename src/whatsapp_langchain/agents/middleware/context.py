"""Factory para middlewares de gerenciamento de contexto.

Este módulo fornece uma interface unificada para escolher entre diferentes
estratégias de gerenciamento de contexto via variável de ambiente.

Estratégias disponíveis:
    - trim: Remove turnos antigos (custo zero, perde contexto)
    - summarize: Sumariza mensagens antigas (custo extra, preserva contexto)
    - none: Sem gerenciamento (para testes ou conversas curtas)

Configuração via .env:
    CONTEXT_STRATEGY=trim              # trim | summarize | none

    # Para TRIM:
    TRIM_KEEP_TURNS=5                  # Turnos recentes a manter

    # Para SUMMARIZE:
    SUMMARIZE_TRIGGER_TOKENS=4000      # Tokens antes de sumarizar
    SUMMARIZE_KEEP_MESSAGES=10         # Mensagens a manter após sumarização
    SUMMARIZE_MODEL=anthropic/claude-3-haiku  # Modelo para sumarização

Exemplo:
    from whatsapp_langchain.agents.middleware import get_context_middleware

    # Lê configuração do .env automaticamente
    middlewares = get_context_middleware()

    agent = create_agent(
        model=model,
        middleware=middlewares,
        ...
    )
"""

from typing import Any

from whatsapp_langchain.agents.middleware.summarize import create_summarize_middleware
from whatsapp_langchain.agents.middleware.trim import create_trim_middleware
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.llm import create_chat_model


def get_context_middleware(
    strategy: str | None = None,
    trim_keep_turns: int | None = None,
    summarize_trigger_tokens: int | None = None,
    summarize_keep_messages: int | None = None,
    summarize_model: str | None = None,
    summarize_prompt: str | None = None,
) -> list[Any]:
    """Retorna lista de middlewares baseado na estratégia configurada.

    Lê defaults de `shared.config.settings`, mas permite override via parâmetros.

    Args:
        strategy: Estratégia de contexto (trim/summarize/none).
                  Default: settings.context_strategy.
        trim_keep_turns: Turnos recentes a manter no trim.
                         Default: settings.trim_keep_turns.
        summarize_trigger_tokens: Tokens antes de acionar sumarização.
                                  Default: settings.summarize_trigger_tokens.
        summarize_keep_messages: Mensagens a manter após sumarização.
                                 Default: settings.summarize_keep_messages.
        summarize_model: Modelo para sumarização.
                         Default: settings.summarize_model.
        summarize_prompt: Prompt customizado para sumarização.
                          Default: prompt padrão em português (ver summarize.py).

    Returns:
        Lista de middlewares para passar ao create_agent().
        Lista vazia se strategy="none".

    Exemplo:
        # Usando configuração do .env
        middlewares = get_context_middleware()

        # Override para testes
        middlewares = get_context_middleware(strategy="trim", trim_keep_turns=3)
    """
    middlewares: list[Any] = []

    # Context strategy (trim/summarize/none)
    resolved_strategy = strategy or settings.context_strategy

    if resolved_strategy == "trim":
        resolved_keep = (
            trim_keep_turns if trim_keep_turns is not None else settings.trim_keep_turns
        )
        middlewares.append(create_trim_middleware(keep_turns=resolved_keep))

    elif resolved_strategy == "summarize":
        resolved_tokens = (
            summarize_trigger_tokens
            if summarize_trigger_tokens is not None
            else settings.summarize_trigger_tokens
        )
        resolved_keep = (
            summarize_keep_messages
            if summarize_keep_messages is not None
            else settings.summarize_keep_messages
        )
        resolved_model = summarize_model or settings.summarize_model
        middlewares.append(
            create_summarize_middleware(
                model=create_chat_model(model=resolved_model, temperature=0.0),
                trigger_tokens=resolved_tokens,
                keep_messages=resolved_keep,
                prompt=summarize_prompt,
            )
        )

    return middlewares
