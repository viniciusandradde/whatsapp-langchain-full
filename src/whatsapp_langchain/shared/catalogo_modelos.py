"""Catálogo completo de modelos pro seletor do agente (ADR-004).

Lê `openrouter_modelo` (mig 178, sincronizado a cada 10 min pelo worker) e
devolve, por modelo, o que o card do painel precisa: capacidades derivadas
das modalidades/parâmetros, preço por token, selo de curado (`modelo_llm`),
novidade, promoção e "em alta" (top 20 do ranking diário da mig 179).

É leitura pura — quem escreve no catálogo é `openrouter_catalogo.py`. O
resultado é o mesmo pra toda empresa, por isso o cache é por processo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from psycopg_pool import AsyncConnectionPool

# Nome de exibição por prefixo do slug. Fora do mapa: capitalize().
PROVEDORES_NOME: dict[str, str] = {
    "google": "Google",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "qwen": "Qwen",
    "deepseek": "Deepseek",
    "moonshotai": "Moonshot AI",
    "amazon": "Amazon",
    "meta-llama": "Meta",
    "mistralai": "Mistral",
    "x-ai": "xAI",
    "z-ai": "Z.ai",
    "microsoft": "Microsoft",
    "cohere": "Cohere",
    "perplexity": "Perplexity",
    "nvidia": "NVIDIA",
    "minimax": "MiniMax",
    "tencent": "Tencent",
    "baidu": "Baidu",
}

# Modelo publicado no OpenRouter há menos que isto ganha o selo "novo".
NOVO_DIAS = 30
# Quantos do ranking diário contam como "em alta".
TOP_TENDENCIA = 20
# O sync do catálogo roda a cada 10 min no worker; cache alinhado.
CACHE_SEGUNDOS = 10 * 60

_SQL_MODELOS = """
SELECT m.slug, m.nome, m.descricao, m.context_length,
       ('image' = ANY(m.input_modalities))                               AS visao,
       ('reasoning' = ANY(m.supported_parameters)
        OR 'include_reasoning' = ANY(m.supported_parameters))            AS pensamento,
       ('tools' = ANY(m.supported_parameters))                           AS tools,
       NULLIF(m.pricing->>'prompt','')::float8                            AS preco_prompt,
       NULLIF(m.pricing->>'completion','')::float8                        AS preco_completion,
       m.criado_no_or,
       EXISTS (SELECT 1 FROM modelo_llm c
                WHERE c.ativo AND c.tipo = 'chat'
                  AND c.provedor || '/' || c.nome = m.slug)              AS curado
  FROM openrouter_modelo m
 WHERE m.ativo
 ORDER BY m.slug
"""

# Top N do dia mais recente do ranking (mig 179). `other` é a linha
# agregada do dataset — está no denominador do share, não no ranking.
_SQL_TENDENCIA = """
SELECT r.slug
  FROM openrouter_ranking_diario r
 WHERE r.data = (SELECT max(data) FROM openrouter_ranking_diario)
   AND r.slug <> 'other'
 GROUP BY r.slug
 ORDER BY sum(r.total_tokens) DESC
 LIMIT %s
"""


def nome_do_provedor(provedor: str) -> str:
    return PROVEDORES_NOME.get(provedor, provedor.capitalize())


def montar_item(
    row: tuple[Any, ...], *, tendencia: set[str], agora: datetime
) -> dict[str, Any]:
    """Uma linha de `_SQL_MODELOS` → item do catálogo (15 chaves, ADR-004 §4.8)."""
    (
        slug,
        nome,
        descricao,
        context_length,
        visao,
        pensamento,
        tools,
        preco_prompt,
        preco_completion,
        criado_no_or,
        curado,
    ) = row
    provedor = slug.split("/")[0]
    novo = bool(criado_no_or) and (agora - criado_no_or).days < NOVO_DIAS
    return {
        "slug": slug,
        "provedor": provedor,
        "provedor_nome": nome_do_provedor(provedor),
        "nome": nome,
        "descricao": descricao,
        "context_length": context_length,
        "visao": bool(visao),
        "pensamento": bool(pensamento),
        "tools": bool(tools),
        "preco_prompt": preco_prompt,
        "preco_completion": preco_completion,
        "novo": novo,
        "tendencia": slug in tendencia,
        "promo": slug.endswith(":free") or preco_prompt == 0,
        "curado": bool(curado),
    }


@dataclass
class _Cache:
    gerado_em: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)


_cache = _Cache()


async def listar_catalogo_modelos(
    pool: AsyncConnectionPool, *, usar_cache: bool = True
) -> dict[str, Any]:
    """`{"itens": [...], "gerado_em": iso}` — cacheado por processo (10 min)."""
    if (
        usar_cache
        and _cache.payload
        and time.monotonic() - _cache.gerado_em < CACHE_SEGUNDOS
    ):
        return _cache.payload

    async with pool.connection() as conn:
        cur = await conn.execute(_SQL_MODELOS)
        rows = await cur.fetchall()
        cur = await conn.execute(_SQL_TENDENCIA, (TOP_TENDENCIA,))
        tendencia = {r[0] for r in await cur.fetchall()}

    agora = datetime.now(UTC)
    payload = {
        "itens": [montar_item(r, tendencia=tendencia, agora=agora) for r in rows],
        "gerado_em": agora.isoformat(),
    }
    _cache.gerado_em = time.monotonic()
    _cache.payload = payload
    return payload


def limpar_cache_catalogo() -> None:
    """Pra testes."""
    _cache.gerado_em = 0.0
    _cache.payload = {}
