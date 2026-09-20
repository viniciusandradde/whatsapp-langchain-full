"""Tiers de contexto do agente (ADR-004) — fonte única de chars, tokens e créditos.

O tier (`agente_ia.contexto_tamanho`) diz quantos caracteres de histórico o
agente relê a cada resposta; o worker corta por aqui (`middleware/trim.py`,
`max_chars`). O mesmo número alimenta a estimativa de créditos que o painel
mostra em cada modelo — por isso a tabela e a fórmula moram num lugar só, e
o espelho em TypeScript (`creditos.ts`) tem os mesmos valores de teste.

Crédito é unidade de EXIBIÇÃO (1 C = US$ 0,001), não de cobrança: o custo
real continua em `ia_execucao`.
"""

from __future__ import annotations

import math
from typing import Literal

TierContexto = Literal["lite", "regular", "medium", "large", "extended"]

# Caracteres de histórico por tier.
TIERS: dict[str, int] = {
    "lite": 6_000,
    "regular": 15_000,
    "medium": 25_000,
    "large": 35_000,
    "extended": 300_000,
}
ORDEM: tuple[str, ...] = ("lite", "regular", "medium", "large", "extended")
# Só sinalização visual nesta leva (D3): nada trava.
PREMIUM: frozenset[str] = frozenset({"medium", "large", "extended"})
TIER_PADRAO: TierContexto = "lite"

# Aproximação de tokens (÷4) — o mesmo chute que o painel usa.
CHARS_POR_TOKEN = 4
# Tamanho típico de UMA resposta do agente, pra estimar o lado da saída.
TOKENS_SAIDA_ESTIMADOS = 300
USD_POR_CREDITO = 0.001


def chars_para_tokens(chars: int) -> int:
    return max(1, chars // CHARS_POR_TOKEN)


def creditos_por_mensagem(
    *, preco_prompt: float | None, preco_completion: float | None, tier: str
) -> int | None:
    """Créditos estimados de UMA resposta com o histórico cheio no tier.

    `preco_*` em US$ por token (como vem no `pricing` do OpenRouter). None
    quando o preço é desconhecido — o card mostra `?` nesse caso.
    """
    if preco_prompt is None or preco_completion is None:
        return None
    usd = (
        chars_para_tokens(TIERS[tier]) * preco_prompt
        + TOKENS_SAIDA_ESTIMADOS * preco_completion
    )
    return max(1, math.ceil(usd / USD_POR_CREDITO))


# ---- Gate por plano (mig 188) --------------------------------------------

# Preço de ENTRADA (US$/token) acima do qual o modelo é "premium": só planos
# com `modelos_premium`. US$ 5/Mtok é onde ficam os modelos de topo.
PRECO_PROMPT_PREMIUM = 5e-6


def tier_maximo_de(features: dict | None) -> TierContexto:
    """`plano.features['contexto_max']` validado; ausente ou inválido = `lite`.

    Plano sem a chave (custom, ou anterior à mig 188) fica no mais barato:
    o mesmo "sem feature = sem recurso" da voz — errar para o lado do custo
    baixo, nunca liberar Extended sem querer.
    """
    valor = (features or {}).get("contexto_max")
    return valor if valor in TIERS else "lite"  # type: ignore[return-value]


def tier_permitido(tier: str, maximo: str) -> bool:
    return ORDEM.index(tier) <= ORDEM.index(maximo)


def limitar_tier(tier: str, maximo: str) -> str:
    """O menor dos dois — é o que o worker aplica."""
    return tier if tier_permitido(tier, maximo) else maximo


def modelo_e_premium(preco_prompt: float | None) -> bool:
    return preco_prompt is not None and preco_prompt > PRECO_PROMPT_PREMIUM
