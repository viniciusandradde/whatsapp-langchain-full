"""Testes da política de retenção de dados (Fase E).

A regra `max(empresa, agente)` com semântica de NULL/ilimitado é destrutiva —
erro aqui apaga conversa de cliente antes da hora ou nunca. Cobre a matriz
inteira. O expurgo em si (SQL + storage + checkpointer) é validado no dev com
atendimentos encerrados antigos (marcador docker_demo).
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.dados_retencao import retencao_efetiva_dias


class TestRetencaoEfetiva:
    def test_empresa_none_e_ilimitado(self) -> None:
        # Empresa sem prazo = ilimitado, mesmo com agente finito (só estende).
        assert retencao_efetiva_dias(None, None) is None
        assert retencao_efetiva_dias(None, 30) is None
        assert retencao_efetiva_dias(None, 365) is None

    def test_empresa_zero_e_ilimitado(self) -> None:
        # 0 no dropdown = "Ilimitado" (igual a NULL para efeito de expurgo).
        assert retencao_efetiva_dias(0, None) is None
        assert retencao_efetiva_dias(0, 90) is None

    def test_agente_none_herda_empresa(self) -> None:
        assert retencao_efetiva_dias(90, None) == 90
        assert retencao_efetiva_dias(30, None) == 30

    def test_agente_zero_e_ilimitado(self) -> None:
        # Agente pode "segurar pra sempre" mesmo com a empresa em 90d.
        assert retencao_efetiva_dias(90, 0) is None

    def test_agente_estende_alem_da_empresa(self) -> None:
        assert retencao_efetiva_dias(90, 365) == 365
        assert retencao_efetiva_dias(30, 180) == 180

    def test_agente_nao_encurta_abaixo_da_empresa(self) -> None:
        # Agente 30 com empresa 90 NÃO reduz — o agente só estende (max).
        assert retencao_efetiva_dias(90, 30) == 90
        assert retencao_efetiva_dias(90, 90) == 90

    @pytest.mark.parametrize(
        ("empresa", "agente", "esperado"),
        [
            (None, None, None),
            (None, 30, None),
            (0, 0, None),
            (90, None, 90),
            (90, 0, None),
            (90, 30, 90),
            (90, 180, 180),
            (365, 90, 365),
        ],
    )
    def test_matriz(
        self, empresa: int | None, agente: int | None, esperado: int | None
    ) -> None:
        assert retencao_efetiva_dias(empresa, agente) == esperado
