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

from dataclasses import dataclass

import structlog
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


_log_llm = structlog.get_logger()

_SEM_PROVEDOR_PERMITIDO = "no allowed providers"


def erro_e_sem_provedor_permitido(exc: BaseException) -> bool:
    """404 do OpenRouter "No allowed providers are available for the selected
    model": os provedores que servem o modelo hoje não passam no piso de
    quantização acima. Aconteceu em 21/09/2026 com deepseek-v4.1-flash — o
    OpenRouter re-apontou o apelido para uma versão datada servida só por
    Morph/Relace (fp4) e o agente da VSA ficou mudo das 08:20 às 10:00."""
    return _SEM_PROVEDOR_PERMITIDO in str(exc).lower()


class ChatOpenAIResiliente(ChatOpenAI):
    """ChatOpenAI que, num 404 "sem provedor permitido", repete UMA vez sem o
    piso de quantização (decisão do dono, 21/09/2026): responder pelo provedor
    fp4 é melhor que ficar mudo. O relaxamento é por chamada — o bloco
    `provider` original continua nas seguintes — e fica no log; a sonda de
    disponibilidade (`sondar_modelo`) abre o alerta no canal em até 10 min."""

    def _sem_piso(self) -> ChatOpenAI:
        return self.model_copy(update={"extra_body": None})

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        try:
            return await super()._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 — só o 404 específico é tratado
            if not (self.extra_body and erro_e_sem_provedor_permitido(exc)):
                raise
            _log_llm.warning(
                "roteamento_relaxado", model=self.model_name, error=str(exc)[:160]
            )
            return await self._sem_piso()._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        try:
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception as exc:  # noqa: BLE001
            if not (self.extra_body and erro_e_sem_provedor_permitido(exc)):
                raise
            _log_llm.warning(
                "roteamento_relaxado", model=self.model_name, error=str(exc)[:160]
            )
            return self._sem_piso()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )


@dataclass(frozen=True)
class SondaModelo:
    """Resultado da chamada mínima real a um modelo (1 token)."""

    slug: str
    ok: bool
    codigo: int | None
    motivo: str
    inexistente: bool = False  # 404/400 "modelo não existe": nem sem piso responde
    sem_provedor_permitido: bool = False  # 404 com piso; responde sem piso
    transitorio: bool = False  # 429/5xx/timeout: não muda estado nenhum


def classificar_sonda(
    slug: str,
    codigo_com_piso: int | None,
    corpo_com_piso: str,
    codigo_sem_piso: int | None,
) -> SondaModelo:
    """Pura: traduz os dois status (com e sem piso) na conclusão da sonda.
    `codigo_sem_piso=None` = não foi preciso (a primeira respondeu)."""
    if codigo_com_piso is not None and 200 <= codigo_com_piso < 300:
        return SondaModelo(slug, True, codigo_com_piso, "responde")
    corpo = (corpo_com_piso or "").lower()
    if codigo_com_piso == 404 and _SEM_PROVEDOR_PERMITIDO in corpo:
        if codigo_sem_piso is not None and 200 <= codigo_sem_piso < 300:
            return SondaModelo(
                slug,
                False,
                404,
                "só provedores abaixo do piso de quantização (respondendo sem o piso)",
                sem_provedor_permitido=True,
            )
        return SondaModelo(
            slug, False, 404, "sem provedor disponível", inexistente=True
        )
    if codigo_com_piso == 404 or (
        codigo_com_piso == 400
        and any(
            t in corpo
            for t in ("not found", "does not exist", "invalid model", "no endpoints")
        )
    ):
        return SondaModelo(
            slug,
            False,
            codigo_com_piso,
            "modelo não existe mais no OpenRouter",
            inexistente=True,
        )
    if codigo_com_piso == 400:
        # 400 por parâmetro (ex.: modelo de áudio recusando texto puro) não é
        # indisponibilidade — a sonda mínima é que não serve para ele.
        return SondaModelo(
            slug, True, 400, "responde (recusou a chamada mínima por parâmetro)"
        )
    if codigo_com_piso == 402:
        return SondaModelo(
            slug, True, 402, "saldo do OpenRouter esgotado (não é o modelo)"
        )
    if codigo_com_piso is None:
        return SondaModelo(
            slug, False, None, "sem resposta do OpenRouter", transitorio=True
        )
    return SondaModelo(
        slug,
        False,
        codigo_com_piso,
        f"OpenRouter respondeu {codigo_com_piso}",
        transitorio=True,
    )


async def sondar_modelo(slug: str, *, timeout: float = 25.0) -> SondaModelo:
    """Chamada mínima real (1 token) com o MESMO bloco `provider` do runtime.

    É a única prova confiável de disponibilidade: a lista de endpoints do
    apelido `deepseek-v4.1-flash` seguia com 22 provedores enquanto a chamada
    era roteada para a versão datada com 2. Custo ≈ 1 token por modelo em
    uso a cada 10 min."""
    import httpx

    api_key = settings.openrouter_api_key
    if api_key is None:
        return SondaModelo(
            slug, False, None, "sem chave do OpenRouter", transitorio=True
        )
    headers = {
        "Authorization": f"Bearer {api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    base = settings.openrouter_base_url.rstrip("/")

    async def _chamar(com_piso: bool) -> tuple[int | None, str]:
        corpo: dict = {
            "model": slug,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
        }
        prefs = provider_preferences(slug) if com_piso else None
        if prefs is not None:
            corpo["provider"] = prefs
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/chat/completions", json=corpo, headers=headers
                )
        except (httpx.HTTPError, OSError):
            return None, ""
        return resp.status_code, resp.text[:600]

    codigo, texto = await _chamar(com_piso=True)
    codigo_sem_piso: int | None = None
    if codigo == 404 and _SEM_PROVEDOR_PERMITIDO in texto.lower():
        codigo_sem_piso, _ = await _chamar(com_piso=False)
    return classificar_sonda(slug, codigo, texto, codigo_sem_piso)


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

    return ChatOpenAIResiliente(**kwargs)


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
