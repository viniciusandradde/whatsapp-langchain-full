"""Unit dos alertas de degradação de IA (shared/ia_alertas.py, mig 180).

`avaliar_condicoes` é função pura de propósito — estes testes são o contrato
dos limiares (mesmo racional do test de producao_checks): mudar um limiar
sem olhar aqui é quebra consciente.
"""

from __future__ import annotations

from whatsapp_langchain.shared.ia_alertas import (
    ERRO_PROPRIO_MIN_CHAMADAS,
    UPTIME_MINIMO,
    avaliar_condicoes,
    formatar_alerta,
)

_SNAPSHOT_SAUDAVEL = {
    "uptime_30m": 99.8,
    "latencia_p50": 400.0,
    "throughput_p50": 120.0,
    "endpoints": 3,
}
_BASELINE = {
    "latencia_p50": 420.0,
    "throughput_p50": 110.0,
    "tinha_endpoints": True,
}
_OPERACAO_OK = {"chamadas": 50, "erros": 0}


class TestAvaliarCondicoes:
    def test_tudo_saudavel_nao_alerta(self):
        assert avaliar_condicoes(_SNAPSHOT_SAUDAVEL, _BASELINE, _OPERACAO_OK) == []

    def test_uptime_abaixo_do_piso(self):
        snap = {**_SNAPSHOT_SAUDAVEL, "uptime_30m": 94.2}
        achados = avaliar_condicoes(snap, _BASELINE, _OPERACAO_OK)
        assert [a["tipo"] for a in achados] == ["uptime"]
        assert achados[0]["detalhe"]["limiar"] == UPTIME_MINIMO

    def test_latencia_2x_baseline(self):
        snap = {**_SNAPSHOT_SAUDAVEL, "latencia_p50": 900.0}  # 2.14× de 420
        achados = avaliar_condicoes(snap, _BASELINE, _OPERACAO_OK)
        assert [a["tipo"] for a in achados] == ["latencia"]
        assert achados[0]["detalhe"]["fator"] == 2.14

    def test_latencia_sem_baseline_nao_alerta(self):
        # modelo novo sem 7d de série não tem régua — não pode alertar
        snap = {**_SNAPSHOT_SAUDAVEL, "latencia_p50": 5000.0}
        base = {**_BASELINE, "latencia_p50": None}
        assert avaliar_condicoes(snap, base, _OPERACAO_OK) == []

    def test_throughput_na_metade(self):
        snap = {**_SNAPSHOT_SAUDAVEL, "throughput_p50": 40.0}  # 36% de 110
        achados = avaliar_condicoes(snap, _BASELINE, _OPERACAO_OK)
        assert [a["tipo"] for a in achados] == ["throughput"]

    def test_erros_proprios_acima_de_20pct(self):
        achados = avaliar_condicoes(
            _SNAPSHOT_SAUDAVEL, _BASELINE, {"chamadas": 10, "erros": 3}
        )
        assert [a["tipo"] for a in achados] == ["erros_proprios"]
        assert achados[0]["detalhe"]["pct"] == 30.0

    def test_erros_sem_volume_minimo_nao_alerta(self):
        # 1 erro em 2 chamadas é 50% mas não é sinal
        op = {"chamadas": ERRO_PROPRIO_MIN_CHAMADAS - 1, "erros": 2}
        assert avaliar_condicoes(_SNAPSHOT_SAUDAVEL, _BASELINE, op) == []

    def test_modelo_sumiu_exige_historico(self):
        # sem snapshot + TINHA endpoints nos 7d = sumiu
        achados = avaliar_condicoes(None, _BASELINE, _OPERACAO_OK)
        assert [a["tipo"] for a in achados] == ["modelo_sumiu"]
        # sem snapshot + nunca teve = modelo novo, silêncio
        base = {**_BASELINE, "tinha_endpoints": False}
        assert avaliar_condicoes(None, base, _OPERACAO_OK) == []

    def test_snapshot_sem_endpoints_conta_como_sumido(self):
        snap = {**_SNAPSHOT_SAUDAVEL, "endpoints": 0}
        achados = avaliar_condicoes(snap, _BASELINE, _OPERACAO_OK)
        assert [a["tipo"] for a in achados] == ["modelo_sumiu"]

    def test_condicoes_acumulam(self):
        snap = {
            "uptime_30m": 90.0,
            "latencia_p50": 2000.0,
            "throughput_p50": 10.0,
            "endpoints": 2,
        }
        achados = avaliar_condicoes(snap, _BASELINE, {"chamadas": 20, "erros": 10})
        assert {a["tipo"] for a in achados} == {
            "uptime",
            "latencia",
            "throughput",
            "erros_proprios",
        }


class TestFormatarAlerta:
    def test_mensagens_legiveis_sem_jargao(self):
        m = formatar_alerta("google/gemini-2.5-flash", "uptime", {"valor": 94.2})
        assert "94.2%" in m and "google/gemini-2.5-flash" in m
        m = formatar_alerta("a/b", "latencia", {"valor_ms": 900.0, "fator": 2.14})
        assert "900ms" in m and "2.14×" in m
        m = formatar_alerta("a/b", "modelo_sumiu", {})
        assert "não aparece" in m
