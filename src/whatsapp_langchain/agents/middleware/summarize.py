"""Middleware de Summarize para gerenciamento de contexto.

O summarize é a estratégia mais sofisticada para gerenciar contexto:
sumariza mensagens antigas preservando informações importantes.

Trade-offs:
    - Custo: Uma chamada LLM extra por sumarização
    - Contexto: Preservado (resumo mantém informações chave)
    - Latência: Adicional (tempo da chamada de sumarização)

Quando usar:
    - Chatbots onde histórico é importante (atendimento, vendas)
    - Conversas longas que precisam de contexto
    - Quando qualidade é prioridade sobre custo

Exemplo:
    from whatsapp_langchain.agents.middleware.summarize import (
        create_summarize_middleware,
        DEFAULT_PROMPT,
    )

    summarize = create_summarize_middleware(
        model=my_cheap_model,
        trigger_tokens=4000,
        keep_messages=10,
    )
    agent = create_agent(model=model, middleware=[summarize], ...)
"""

from langchain.agents.middleware import SummarizationMiddleware
from langchain_openai import ChatOpenAI

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.llm import create_chat_model

# Prompt padrão para sumarização em português
# O placeholder {messages} é OBRIGATÓRIO - o LangChain insere o histórico aqui
DEFAULT_PROMPT = """Resuma a conversa a seguir de forma concisa.

## Conversa
{messages}

## Instruções

Mantenha no resumo:
- Nome do usuário e informações pessoais mencionadas
- Preferências e interesses expressos
- Decisões ou acordos feitos
- Contexto importante para continuar a conversa

Ignore:
- Saudações e despedidas
- Repetições
- Detalhes triviais

Escreva o resumo em português brasileiro, em no máximo 3-4 frases."""


def create_summarize_middleware(
    model: ChatOpenAI | None = None,
    trigger_tokens: int = 4000,
    keep_messages: int = 10,
    prompt: str | None = None,
) -> SummarizationMiddleware:
    """Cria middleware que sumariza mensagens antigas.

    Quando o histórico excede `trigger_tokens`, o middleware sumariza
    as mensagens antigas e mantém apenas as `keep_messages` mais recentes
    junto com o resumo.

    Args:
        model: Modelo para sumarização. Se None, cria um usando env vars.
               Recomendado usar um modelo barato/rápido.
        trigger_tokens: Tokens antes de acionar sumarização.
                        Default: 4000.
        keep_messages: Mensagens recentes a manter após sumarização.
                       Default: 10.
        prompt: Prompt customizado para sumarização.
                Default: prompt em português focado em preservar contexto.

    Returns:
        SummarizationMiddleware configurado.

    Exemplo:
        Conversa com 8000 tokens, trigger=4000, keep=4:

        Antes:  [system] [u1] [a1] [u2] [a2] ... [u10] [a10]
        Depois: [system] [summary] [u9] [a9] [u10] [a10]

        O [summary] contém um resumo das mensagens u1-u8/a1-a8.
    """
    resolved_prompt = prompt or DEFAULT_PROMPT

    # Se não passou modelo, cria usando factory centralizada (shared/llm.py)
    if model is None:
        model = create_chat_model(
            model=settings.summarize_model,
            temperature=0.0,  # Determinístico para resumos consistentes
        )

    return SummarizationMiddleware(
        model=model,
        trigger=("tokens", trigger_tokens),
        keep=("messages", keep_messages),
        summary_prompt=resolved_prompt,
    )
