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

# ---------------------------------------------------------------------------
# Política de roteamento OpenRouter (ADR-001, docs/ADR-001-roteamento-openrouter.md)
#
# Modelo de peso aberto no OpenRouter é servido por MUITOS hosts terceiros
# (deepseek-v3.2: 14 provedores, alguns em fp4) e o roteador padrão escolhe
# pelo preço — a request de um cliente pode cair calada num host quantizado
# degradado. O piso abaixo barra isso sem manter lista nominal de provedores,
# que envelhece e ainda não tem tráfego real pra ser calibrada.
#
# Modelo proprietário fica SEM bloco `provider` de propósito: Gemini/GPT/
# Claude/Grok só têm endpoints 1st-party (Gemini: 2, ambos da própria Google)
# e o load-balance padrão do OpenRouter já faz o failover entre eles —
# qualquer preferência explícita DESLIGA esse balanceamento. Não "melhorar".
# ---------------------------------------------------------------------------

QUANTIZACOES_ACEITAS = ["fp8", "bf16", "fp16", "fp32"]

_PREFIXOS_PROPRIETARIOS = ("google/", "openai/", "anthropic/", "x-ai/")


def provider_preferences(model: str) -> dict | None:
    """Bloco `provider` do OpenRouter pra este modelo, ou None.

    None = não enviar bloco nenhum (proprietário; o default do OpenRouter já
    é o ótimo). Dict = piso de quantização pra peso aberto; `allow_fallbacks`
    continua no default (true) — a redundância entre hosts é o motivo de usar
    OpenRouter, restringir demais a derruba.
    """
    if model.startswith(_PREFIXOS_PROPRIETARIOS):
        return None
    return {"quantizations": QUANTIZACOES_ACEITAS}


# Catálogo curado de modelos disponíveis no painel para swap por agente.
# Mantenha em sincronia com o frontend (/models) — qualquer string é aceita
# pelo backend, mas só essas aparecem no select.
CURATED_MODELS: list[dict[str, str]] = [
    {"id": "x-ai/grok-4.5", "label": "Grok 4.5", "type": "chat"},
    {"id": "x-ai/grok-4.3", "label": "Grok 4.3", "type": "chat"},
    {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini", "type": "chat"},
    {"id": "openai/gpt-4o", "label": "GPT-4o", "type": "chat"},
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5", "type": "chat"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "type": "chat"},
    {"id": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "type": "chat"},
    {
        "id": "google/gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite",
        "type": "chat",
    },
    {
        # Variante GA, NÃO a `-preview`: o sufixo -preview exige opt-in de
        # compartilhamento de dados na conta OpenRouter e devolve 404
        # ("No endpoints available matching your guardrail restrictions and
        # data policy") sem ele. Mesmo preço, mesma janela, mesmas
        # modalidades. Ver mig 140.
        "id": "google/gemini-3.1-flash-lite",
        "label": "Gemini 3.1 Flash Lite",
        "type": "chat",
    },
    {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "type": "chat"},
    {"id": "deepseek/deepseek-v3.2", "label": "DeepSeek V3.2", "type": "chat"},
    {"id": "z-ai/glm-4.5-air", "label": "GLM 4.5 Air", "type": "chat"},
    {"id": "z-ai/glm-4.7-flash", "label": "GLM 4.7 Flash", "type": "chat"},
    {"id": "tencent/hy3-preview", "label": "Tencent HY3 Preview", "type": "chat"},
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
    {
        "id": "qwen/qwen2.5-vl-72b-instruct",
        "label": "Qwen2.5 VL 72B",
        "type": "media",
    },
    {
        "id": "qwen/qwen3-vl-30b-a3b-instruct",
        "label": "Qwen3 VL 30B",
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
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Cria ChatOpenAI configurado com rate limiter.

    O rate limiter usa token bucket: limita requisições por segundo
    com burst para picos controlados. Valores vêm de settings
    (LLM_RATE_LIMIT_REQUESTS_PER_SECOND e LLM_RATE_LIMIT_MAX_BURST).

    Args:
        model: Nome do modelo. Default: settings.openrouter_model.
        temperature: Temperatura. Default: None (usa default do provider).
        top_p: Nucleus sampling. Default: None (usa default do provider).
        max_tokens: Limite de tokens da resposta. Default: None.

    Returns:
        ChatOpenAI com rate limiter aplicado.
    """
    api_key = settings.openrouter_api_key
    secret_key = SecretStr(api_key.get_secret_value()) if api_key else None

    # O limiter é por PROCESSO e a setting é por SLOT do worker: com N
    # mensagens em voo, o teto escala junto — senão 0,5 rps (30 chamadas/min)
    # engoliria toda a concorrência. Na API `worker_concurrency` fica em 1.
    rate_limiter = _get_rate_limiter(
        requests_per_second=(
            settings.llm_rate_limit_requests_per_second * settings.worker_concurrency
        ),
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
    if top_p is not None:
        kwargs["top_p"] = top_p
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    prefs = provider_preferences(kwargs["model"])
    if prefs is not None:
        # ChatOpenAI repassa `extra_body` verbatim no JSON da request.
        kwargs["extra_body"] = {"provider": prefs}

    return ChatOpenAI(**kwargs)


async def get_agent_llm_config(
    pool: AsyncConnectionPool, agent_id: str, empresa_id: int = 1
) -> tuple[str, str]:
    """Resolve (chat_model, midia_model) para (empresa, agente) com hot reload.

    Lê a tabela `agent_llm_config` usando a PK composta (empresa_id, agent_id).
    Quando a row está ausente ou um campo é NULL, faz fallback para
    `settings.openrouter_model` / `settings.openrouter_midia_model`. Sem
    cache — uma query por chamada.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT chat_model, midia_model FROM agent_llm_config
             WHERE empresa_id = %s AND agent_id = %s
            """,
            (empresa_id, agent_id),
        )
        row = await cur.fetchone()
    chat = (row[0] if row else None) or settings.openrouter_model
    midia = (row[1] if row else None) or settings.openrouter_midia_model
    return chat, midia
