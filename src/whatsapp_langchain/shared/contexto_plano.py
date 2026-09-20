"""Gate por plano do tamanho do contexto e dos modelos premium (mig 188).

Fica separado de `contexto.py` (puro) porque lê o banco: o plano da empresa
(`plano_limits.get_plano_info`, cache 30 s) e o preço do modelo no catálogo
(`openrouter_modelo`). Usado em dois lugares:

- rota `PUT /api/v1/agentes/{slug}`: `checar_gate_plano` → 402 legível;
- painel: `resumo_plano` vai junto do catálogo para a tela travar o que o
  plano não tem, antes de o operador tentar salvar.

O worker NÃO usa isto: o loader aplica `limitar_tier` direto sobre o
`PlanoInfo` — sem 402, só rebaixa (downgrade de plano não pode derrubar
o agente).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.contexto import (
    TIERS,
    modelo_e_premium,
    tier_permitido,
)
from whatsapp_langchain.shared.plano_limits import PlanoInfo, get_plano_info

ROTULO_TIER = {
    "lite": "Lite",
    "regular": "Regular",
    "medium": "Medium",
    "large": "Large",
    "extended": "Extended",
}


@dataclass(frozen=True)
class BloqueioPlano:
    """O que a rota transforma em 402 (`detail` no formato do `assert_plano_feature`)."""

    feature: str  # "contexto_max" | "modelos_premium"
    mensagem: str
    plano_atual: str
    upgrade_to: str | None

    def detail(self) -> dict[str, Any]:
        return {
            "error": "feature_unavailable",
            "feature": self.feature,
            "plano_atual": self.plano_atual,
            "upgrade_to": self.upgrade_to,
            "message": self.mensagem,
        }


def _sugestao(plano: PlanoInfo) -> str:
    upg = plano.upgrade_sugerido()
    return f" Faça upgrade para o plano {upg.title()} para liberar." if upg else ""


async def preco_prompt_do_modelo(pool: AsyncConnectionPool, slug: str) -> float | None:
    """US$/token de entrada no catálogo; None se o modelo não está lá."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT NULLIF(pricing->>'prompt','')::float8 FROM openrouter_modelo WHERE slug = %s",
            (slug,),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def checar_gate_plano(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    contexto_tamanho: str | None,
    modelo_slug: str | None,
) -> BloqueioPlano | None:
    """Primeiro bloqueio encontrado, ou None quando o plano comporta tudo.

    `contexto_tamanho`/`modelo_slug` são o que o PATCH está tentando
    gravar (None = não mexe). Modelo fora do catálogo passa: sem preço não
    há como chamar de premium, e recusar travaria modelo legado.
    """
    plano = await get_plano_info(pool, empresa_id)

    if contexto_tamanho and not tier_permitido(contexto_tamanho, plano.contexto_max):
        return BloqueioPlano(
            feature="contexto_max",
            mensagem=(
                f"O tamanho de contexto {ROTULO_TIER[contexto_tamanho]} não está no plano "
                f"{plano.plano_nome} — ele libera até {ROTULO_TIER[plano.contexto_max]} "
                f"({TIERS[plano.contexto_max]:,} caracteres).".replace(",", ".")
                + _sugestao(plano)
            ),
            plano_atual=plano.plano_slug,
            upgrade_to=plano.upgrade_sugerido(),
        )

    if modelo_slug and not plano.modelos_premium:
        preco = await preco_prompt_do_modelo(pool, modelo_slug)
        if modelo_e_premium(preco):
            return BloqueioPlano(
                feature="modelos_premium",
                mensagem=(
                    f"O modelo {modelo_slug} é premium (entrada acima de US$ 5 por milhão "
                    f"de tokens) e não está no plano {plano.plano_nome}."
                    + _sugestao(plano)
                ),
                plano_atual=plano.plano_slug,
                upgrade_to=plano.upgrade_sugerido(),
            )

    return None


def resumo_plano(plano: PlanoInfo) -> dict[str, Any]:
    """O que a tela do seletor precisa para travar tiers e modelos."""
    return {
        "slug": plano.plano_slug,
        "nome": plano.plano_nome,
        "contexto_max": plano.contexto_max,
        "modelos_premium": plano.modelos_premium,
        "catalogo_completo": plano.tem_feature("catalogo_completo"),
        "upgrade_sugerido": plano.upgrade_sugerido(),
    }
