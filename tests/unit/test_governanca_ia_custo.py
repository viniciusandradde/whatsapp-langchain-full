"""Custo de execução LLM: medido pela OpenRouter, estimado só como fallback.

Contexto (2026-07-26): o painel mostrava 13,32 USD para o agente do Luis
Fernando quando o custo real era ~6,96 USD — erro de +91%. `calc_custo()`
recebia `tokens_cached` mas nunca usava, cobrando 48,6M de tokens de input a
preço cheio quando 46,9M (96,5%) eram cache hit, que o DeepSeek cobra pela
metade.

A correção de fundo foi parar de estimar: a OpenRouter devolve `usage.cost` em
toda resposta — o valor efetivamente cobrado, já com desconto de cache, BYOK e
o preço do provedor upstream escolhido no roteamento (medido: 0.2072 USD/Mtok
de prompt contra 0.269 no catálogo).
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.governanca_ia import (
    CUSTO_FONTE_OPENROUTER,
    CUSTO_FONTE_TABELA,
    calc_custo,
)

# Números reais da janela do incidente (empresa 1018, deepseek-v3.2, 1317 execs)
INC_TOK_IN = 48_581_636
INC_TOK_OUT = 498_340
INC_TOK_CACHED = 46_894_592
# Preços reais da OpenRouter para deepseek/deepseek-v3.2 (USD/Mtok)
P_IN, P_OUT, P_CACHE = 0.269, 0.400, 0.1345


class TestCalcCustoComCache:
    """O fallback precisa cobrar cache mais barato que input."""

    def test_reproduz_custo_real_do_incidente(self) -> None:
        """Com 96,5% de cache, o total é ~6,96 e NÃO os 13,32 gravados.

        Este é o teste que trava a regressão original.
        """
        custo = calc_custo(
            INC_TOK_IN,
            INC_TOK_OUT,
            P_IN,
            P_OUT,
            tokens_cached=INC_TOK_CACHED,
            custo_cache_mtok=P_CACHE,
        )

        assert custo == pytest.approx(6.96, abs=0.01), (
            f"esperado ~6.96 USD, veio {custo}. Se deu ~13.32, o cache voltou "
            "a ser cobrado a preço cheio."
        )

    def test_sem_cache_cobra_tudo_como_input(self) -> None:
        """Sem cache hit o resultado é o mesmo da fórmula antiga."""
        custo = calc_custo(1_000_000, 0, P_IN, P_OUT, tokens_cached=0)

        assert custo == pytest.approx(P_IN, abs=1e-9)

    def test_cache_sem_preco_cadastrado_cobra_como_input(self) -> None:
        """Sem `custo_cache_mtok`, superestimar é melhor que zerar em silêncio."""
        com_preco = calc_custo(
            1_000_000, 0, P_IN, P_OUT, tokens_cached=1_000_000, custo_cache_mtok=P_CACHE
        )
        sem_preco = calc_custo(
            1_000_000, 0, P_IN, P_OUT, tokens_cached=1_000_000, custo_cache_mtok=None
        )

        assert com_preco == pytest.approx(P_CACHE, abs=1e-9)
        assert sem_preco == pytest.approx(P_IN, abs=1e-9)
        assert sem_preco > com_preco

    def test_cached_maior_que_input_nao_gera_custo_negativo(self) -> None:
        """Dado inconsistente do provider não pode virar crédito."""
        custo = calc_custo(
            100, 0, P_IN, P_OUT, tokens_cached=999_999, custo_cache_mtok=P_CACHE
        )

        assert custo is not None
        assert custo >= 0

    def test_sem_preco_nenhum_retorna_none(self) -> None:
        assert calc_custo(1000, 100, None, None, tokens_cached=500) is None

    def test_cached_default_zero_mantem_compatibilidade(self) -> None:
        """Chamadas antigas (sem tokens_cached) seguem funcionando."""
        assert calc_custo(1_000_000, 0, P_IN, P_OUT) == pytest.approx(P_IN, abs=1e-9)


class TestProveniencia:
    """As constantes existem pra o relatório distinguir medido de estimado."""

    def test_fontes_sao_distintas_e_estaveis(self) -> None:
        # Gravadas no banco: mudar o valor invalida dados históricos.
        assert CUSTO_FONTE_OPENROUTER == "openrouter"
        assert CUSTO_FONTE_TABELA == "tabela"
        assert CUSTO_FONTE_OPENROUTER != CUSTO_FONTE_TABELA


class TestPreferenciaPeloCustoMedido:
    """O caminho normal usa `usage.cost`; a tabela é rede de segurança.

    Espelha a lógica de `llm_callback.on_llm_end` sem subir o callback inteiro
    (que exigiria pool, LLMResult e run_id).
    """

    @staticmethod
    def _resolver(usage: dict) -> tuple[float | None, str | None]:
        custo_openrouter = usage.get("cost")
        if custo_openrouter is not None and custo_openrouter > 0:
            return float(custo_openrouter), CUSTO_FONTE_OPENROUTER
        custo = calc_custo(
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            P_IN,
            P_OUT,
            tokens_cached=(usage.get("prompt_tokens_details") or {}).get(
                "cached_tokens", 0
            ),
            custo_cache_mtok=P_CACHE,
        )
        return custo, CUSTO_FONTE_TABELA if custo is not None else None

    def test_usa_cost_da_openrouter_quando_presente(self) -> None:
        # Payload real capturado da API (gen-1785096266-BaLnrBxk5b5qeMggbcoG)
        usage = {
            "prompt_tokens": 11,
            "completion_tokens": 5,
            "cost": 3.8332e-06,
            "is_byok": False,
            "prompt_tokens_details": {"cached_tokens": 0},
        }

        custo, fonte = self._resolver(usage)

        assert custo == pytest.approx(3.8332e-06)
        assert fonte == CUSTO_FONTE_OPENROUTER

    def test_cai_pra_tabela_quando_cost_ausente(self) -> None:
        usage = {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "prompt_tokens_details": {"cached_tokens": 1_000_000},
        }

        custo, fonte = self._resolver(usage)

        assert fonte == CUSTO_FONTE_TABELA
        assert custo == pytest.approx(P_CACHE, abs=1e-9)

    def test_cost_zero_nao_mascara_estimativa(self) -> None:
        """cost=0 é ausência de dado, não chamada gratuita — cai pro fallback."""
        usage = {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "cost": 0,
            "prompt_tokens_details": {"cached_tokens": 0},
        }

        custo, fonte = self._resolver(usage)

        assert fonte == CUSTO_FONTE_TABELA
        assert custo == pytest.approx(P_IN, abs=1e-9)
