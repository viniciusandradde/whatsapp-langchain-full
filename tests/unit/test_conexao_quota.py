"""Testes unitários do teto diário + curva de aquecimento (anti-ban, mig 126).

As funções puras (`warmup_cap_for_day`, `effective_cap`) carregam toda a lógica
de decisão do teto — testá-las cobre o coração da feature sem precisar de DB.
"""

from whatsapp_langchain.shared.conexao_quota import (
    WARMUP_BASE,
    WARMUP_DIAS,
    effective_cap,
    warmup_cap_for_day,
)


class TestWarmupCurve:
    def test_dia_zero_eh_base(self):
        assert warmup_cap_for_day(0) == WARMUP_BASE

    def test_curva_cresce(self):
        # cada dia tem teto maior que o anterior até graduar
        anterior = 0
        for d in range(WARMUP_DIAS):
            atual = warmup_cap_for_day(d)
            assert atual is not None
            assert atual > anterior
            anterior = atual

    def test_dia_negativo_trata_como_zero(self):
        assert warmup_cap_for_day(-5) == WARMUP_BASE

    def test_graduado_sem_teto(self):
        assert warmup_cap_for_day(WARMUP_DIAS) is None
        assert warmup_cap_for_day(WARMUP_DIAS + 50) is None

    def test_aproximadamente_1_8x_por_dia(self):
        # dia1 ≈ dia0 * 1.8
        assert warmup_cap_for_day(1) == round(WARMUP_BASE * 1.8)


class TestEffectiveCap:
    def test_sem_teto_nem_aquecimento(self):
        cap, motivo = effective_cap(None, None)
        assert cap is None
        assert motivo is None

    def test_so_teto_manual(self):
        cap, motivo = effective_cap(100, None)
        assert cap == 100
        assert motivo == "teto manual"

    def test_so_aquecimento(self):
        cap, motivo = effective_cap(None, 0)
        assert cap == WARMUP_BASE
        assert "aquecimento" in (motivo or "")

    def test_menor_vence_aquecimento_limita(self):
        # dia 0 (20) é menor que teto manual 500 → aquecimento manda
        cap, motivo = effective_cap(500, 0)
        assert cap == WARMUP_BASE
        assert "aquecimento" in (motivo or "")

    def test_menor_vence_manual_limita(self):
        # teto manual 10 menor que curva do dia 0 (20) → manual manda
        cap, motivo = effective_cap(10, 0)
        assert cap == 10
        assert motivo == "teto manual"

    def test_graduado_cai_no_manual(self):
        cap, motivo = effective_cap(300, WARMUP_DIAS)
        assert cap == 300
        assert motivo == "teto manual"

    def test_graduado_sem_manual_eh_ilimitado(self):
        cap, motivo = effective_cap(None, WARMUP_DIAS)
        assert cap is None
        assert motivo is None
