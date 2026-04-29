"""Factory para criação do modelo LLM com rate limiting.

Centraliza a criação do ChatOpenAI com InMemoryRateLimiter do LangChain.
Todos os pontos que criam modelos devem usar esta factory para garantir
controle de custo uniforme.

Uso:
    from whatsapp_langchain.shared.llm import create_chat_model

    model = create_chat_model()                          # default
    model = create_chat_model(model="gpt-4o-mini")       # override modelo
    model = create_chat_model(temperature=0.0)           # determinístico
"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings

_RATE_LIMITERS: dict[tuple[float, int], InMemoryRateLimiter] = {}

# Catálogo curado de modelos disponíveis no painel para swap por agente.
# Mantenha em sincronia com o frontend (/models) — qualquer string é aceita
# pelo backend, mas só essas aparecem no select.
CURATED_MODELS: list[dict[str, str]] = [
    {"id": "x-ai/grok-4.1-fast", "label": "Grok 4.1 Fast", "type": "chat"},
    {"id": "x-ai/grok-4.1", "label": "Grok 4.1", "type": "chat"},
    {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini", "type": "chat"},
    {"id": "openai/gpt-4o", "label": "GPT-4o", "type": "chat"},
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5", "type": "chat"},
    {"id": "anthropic/claude-sonnet-4.5", "label": "Claude Sonnet 4.5", "type": "chat"},
    {"id": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "type": "chat"},
    {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "type": "chat"},
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "label": "Llama 3.3 70B",
        "type": "chat",
    },
    # Modelos com suporte multimodal (imagem/áudio via OpenRouter).
    {
        "id": "google/gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite",
        "type": "media",
    },
    {"id": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "type": "media"},
    {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini", "type": "media"},
    {
        "id": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5",
        "type": "media",
    },
]


def _get_rate_limiter(
    requests_per_second: float,
    max_bucket_size: int,
) -> InMemoryRateLimiter:
    """Retorna limiter compartilhado por configuração.

    Reusa a mesma instância entre modelos com os mesmos parâmetros para que
    o bucket represente o throughput real do processo (e não de uma chamada).
    """
    key = (requests_per_second, max_bucket_size)
    if key not in _RATE_LIMITERS:
        _RATE_LIMITERS[key] = InMemoryRateLimiter(
            requests_per_second=requests_per_second,
            max_bucket_size=max_bucket_size,
        )
    return _RATE_LIMITERS[key]


def create_chat_model(
    model: str | None = None,
    temperature: float | None = None,
) -> ChatOpenAI:
    """Cria ChatOpenAI configurado com rate limiter.

    O rate limiter usa token bucket: limita requisições por segundo
    com burst para picos controlados. Valores vêm de settings
    (LLM_RATE_LIMIT_REQUESTS_PER_SECOND e LLM_RATE_LIMIT_MAX_BURST).

    Args:
        model: Nome do modelo. Default: settings.openrouter_model.
        temperature: Temperatura. Default: None (usa default do provider).

    Returns:
        ChatOpenAI com rate limiter aplicado.
    """
    api_key = settings.openrouter_api_key
    secret_key = SecretStr(api_key.get_secret_value()) if api_key else None

    rate_limiter = _get_rate_limiter(
        requests_per_second=settings.llm_rate_limit_requests_per_second,
        max_bucket_size=settings.llm_rate_limit_max_burst,
    )

    kwargs: dict = {
        "model": model or settings.openrouter_model,
        "api_key": secret_key,
        "base_url": settings.openrouter_base_url,
        "rate_limiter": rate_limiter,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    return ChatOpenAI(**kwargs)


async def get_agent_llm_config(
    pool: AsyncConnectionPool, agent_id: str
) -> tuple[str, str]:
    """Resolve (chat_model, midia_model) para um agente, com hot reload via DB.

    Lê a tabela `agent_llm_config`. Quando a row está ausente ou um campo é
    NULL, faz fallback para `settings.openrouter_model` /
    `settings.openrouter_midia_model`. Sem cache — uma query por chamada.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT chat_model, midia_model FROM agent_llm_config WHERE agent_id = %s",
            (agent_id,),
        )
        row = await cur.fetchone()
    chat = (row[0] if row else None) or settings.openrouter_model
    midia = (row[1] if row else None) or settings.openrouter_midia_model
    return chat, midia
