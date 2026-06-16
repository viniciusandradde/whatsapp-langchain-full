"""Testes unitários de compliance: detecção de opt-out + kill-switch (Task 8.5)."""

from whatsapp_langchain.shared.campanha import _should_kill_switch
from whatsapp_langchain.shared.opt_out import is_opt_out_request


class TestIsOptOutRequest:
    def test_palavras_chave(self):
        for kw in ["stop", "STOP", "Parar", " sair ", "cancelar", "unsubscribe"]:
            assert is_opt_out_request(kw) is True

    def test_nao_opt_out(self):
        for txt in ["olá", "quero comprar", "stop agora", "", None]:
            assert is_opt_out_request(txt) is False


class TestKillSwitch:
    def test_desligado_quando_pct_none_ou_zero(self):
        assert _should_kill_switch(0, 100, None) is False
        assert _should_kill_switch(0, 100, 0) is False

    def test_nao_age_antes_da_amostra_minima(self):
        # 5 falhas de 5 = 100%, mas < min_amostra (20) → não aborta
        assert _should_kill_switch(0, 5, 30) is False

    def test_aborta_acima_do_limite(self):
        # 10 enviados + 15 falhas = 25 tentados, 60% falha > 30%
        assert _should_kill_switch(10, 15, 30) is True

    def test_nao_aborta_abaixo_do_limite(self):
        # 80 enviados + 5 falhas = 85 tentados, ~5.9% < 30%
        assert _should_kill_switch(80, 5, 30) is False

    def test_min_amostra_customizavel(self):
        assert _should_kill_switch(2, 3, 30, min_amostra=5) is True  # 60% de 5
