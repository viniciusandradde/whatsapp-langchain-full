"""Tiers de contexto e créditos estimados (ADR-004, `shared/contexto.py`).

Os valores aqui são os mesmos do espelho em TypeScript (`creditos.ts`): se um
mudar, o outro tem que mudar junto.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.contexto import (
    ORDEM,
    PRECO_PROMPT_PREMIUM,
    PREMIUM,
    TIER_PADRAO,
    TIERS,
    chars_para_tokens,
    creditos_por_mensagem,
    limitar_tier,
    modelo_e_premium,
    tier_maximo_de,
    tier_permitido,
)

# Gemini 2.5 Flash no OpenRouter: US$ 0,30 / Mtok de entrada, US$ 2,50 de saída.
_FLASH_PROMPT = 3e-7
_FLASH_COMPLETION = 2.5e-6


def test_tiers_em_ordem_crescente_e_default_lite() -> None:
    assert list(TIERS) == list(ORDEM)
    assert [TIERS[t] for t in ORDEM] == sorted(TIERS[t] for t in ORDEM)
    assert TIER_PADRAO == "lite"
    assert PREMIUM == {"medium", "large", "extended"}


def test_chars_para_tokens_divide_por_quatro() -> None:
    assert chars_para_tokens(6_000) == 1_500
    assert chars_para_tokens(300_000) == 75_000
    assert chars_para_tokens(0) == 1  # piso


@pytest.mark.parametrize(
    ("tier", "esperado"),
    [("lite", 2), ("regular", 2), ("medium", 3), ("large", 4), ("extended", 24)],
)
def test_creditos_gemini_flash_por_tier(tier: str, esperado: int) -> None:
    # extended: ceil((75000×3e-7 + 300×2.5e-6) / 0.001) = ceil(23.25) = 24
    assert (
        creditos_por_mensagem(
            preco_prompt=_FLASH_PROMPT, preco_completion=_FLASH_COMPLETION, tier=tier
        )
        == esperado
    )


def test_modelo_gratis_custa_o_minimo_de_um_credito() -> None:
    assert creditos_por_mensagem(preco_prompt=0, preco_completion=0, tier="lite") == 1


def test_preco_desconhecido_devolve_none() -> None:
    assert (
        creditos_por_mensagem(preco_prompt=None, preco_completion=1e-6, tier="lite")
        is None
    )
    assert (
        creditos_por_mensagem(preco_prompt=1e-6, preco_completion=None, tier="lite")
        is None
    )


# ---- Gate por plano (mig 188) ----


def test_tier_maximo_le_o_plano_e_cai_em_lite_sem_chave() -> None:
    assert tier_maximo_de({"contexto_max": "large"}) == "large"
    assert tier_maximo_de({}) == "lite"
    assert tier_maximo_de(None) == "lite"
    assert tier_maximo_de({"contexto_max": "gigante"}) == "lite"


def test_tier_permitido_e_limitar_seguem_a_ordem() -> None:
    assert tier_permitido("lite", "lite")
    assert tier_permitido("regular", "large")
    assert not tier_permitido("extended", "large")
    assert limitar_tier("extended", "regular") == "regular"
    assert limitar_tier("lite", "extended") == "lite"


def test_modelo_premium_e_preco_de_entrada_acima_de_5_por_mtok() -> None:
    assert PRECO_PROMPT_PREMIUM == 5e-6
    assert modelo_e_premium(1.5e-5)
    assert not modelo_e_premium(5e-6)  # Opus/Sonnet a US$ 5 ficam liberados
    assert not modelo_e_premium(None)
