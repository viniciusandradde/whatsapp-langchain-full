"""Testes unitários do jitter anti-ban + resolução de variáveis (Task 6.4)."""

from whatsapp_langchain.shared.campanha import (
    _apply_tokens,
    _jitter_delay_s,
    _resolve_template_vars,
)


class TestApplyTokens:
    def test_nome_primeiro(self):
        assert _apply_tokens("Olá {{nome}}!", "João Silva") == "Olá João!"

    def test_variaveis_csv_chaves_e_colchetes(self):
        out = _apply_tokens(
            "{{nome}} da {{empresa}} / [cidade]",
            "Maria Souza",
            {"empresa": "ACME", "cidade": "SP"},
        )
        assert out == "Maria da ACME / SP"

    def test_sem_nome_token_vira_vazio(self):
        assert _apply_tokens("Oi {{nome}}", None) == "Oi "

    def test_texto_vazio(self):
        assert _apply_tokens("", "João") == ""


class TestResolveTemplateVars:
    def test_resolve_posicional_com_contexto(self):
        base = {"1": "Olá {{nome}}", "2": "Pedido [num]"}
        out = _resolve_template_vars(base, "Ana Lima", {"num": "123"})
        assert out == {"1": "Olá Ana", "2": "Pedido 123"}

    def test_base_vazia(self):
        assert _resolve_template_vars(None, "X") == {}


class TestJitterDelay:
    def test_dentro_da_faixa(self):
        for _ in range(1000):
            d = _jitter_delay_s(3000, 8000)
            assert 3.0 <= d <= 8.0

    def test_min_maior_que_max_troca(self):
        for _ in range(200):
            d = _jitter_delay_s(8000, 3000)
            assert 3.0 <= d <= 8.0

    def test_zero_ou_none(self):
        assert _jitter_delay_s(0, 0) == 0.0
        assert _jitter_delay_s(None, None) == 0.0

    def test_fixo_quando_min_eq_max(self):
        assert _jitter_delay_s(500, 500) == 0.5
