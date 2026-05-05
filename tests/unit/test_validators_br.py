"""Tests dos validadores BR — CPF/CNPJ/CEP/UF (Fase 1.A)."""

from __future__ import annotations

from whatsapp_langchain.shared.validators_br import (
    format_cep,
    format_cnpj,
    format_cpf,
    is_valid_cep,
    is_valid_cnpj,
    is_valid_cpf,
    is_valid_uf,
    normalize_cep,
    normalize_cnpj,
    normalize_cpf,
    only_digits,
)


# ---- CPF ----

class TestCpf:
    def test_cpf_valido_so_digitos(self):
        # CPF de teste comum — 111.444.777-35
        assert is_valid_cpf("11144477735") is True

    def test_cpf_valido_formatado(self):
        assert is_valid_cpf("111.444.777-35") is True

    def test_cpf_invalido_tamanho(self):
        assert is_valid_cpf("123") is False
        assert is_valid_cpf("12345678901234") is False

    def test_cpf_invalido_sequencia_repetida(self):
        assert is_valid_cpf("00000000000") is False
        assert is_valid_cpf("11111111111") is False
        assert is_valid_cpf("99999999999") is False

    def test_cpf_invalido_dv(self):
        assert is_valid_cpf("12345678900") is False  # DV errado

    def test_cpf_none_vazio(self):
        assert is_valid_cpf(None) is False
        assert is_valid_cpf("") is False

    def test_normalize_cpf(self):
        assert normalize_cpf("111.444.777-35") == "11144477735"
        assert normalize_cpf("invalido") is None
        assert normalize_cpf(None) is None

    def test_format_cpf(self):
        assert format_cpf("11144477735") == "111.444.777-35"


# ---- CNPJ ----

class TestCnpj:
    def test_cnpj_valido_so_digitos(self):
        # CNPJ de teste — 11.222.333/0001-81
        assert is_valid_cnpj("11222333000181") is True

    def test_cnpj_valido_formatado(self):
        assert is_valid_cnpj("11.222.333/0001-81") is True

    def test_cnpj_invalido_tamanho(self):
        assert is_valid_cnpj("123") is False

    def test_cnpj_invalido_sequencia(self):
        assert is_valid_cnpj("11111111111111") is False

    def test_cnpj_invalido_dv(self):
        assert is_valid_cnpj("11222333000180") is False

    def test_normalize_cnpj(self):
        assert normalize_cnpj("11.222.333/0001-81") == "11222333000181"
        assert normalize_cnpj("xxx") is None

    def test_format_cnpj(self):
        assert format_cnpj("11222333000181") == "11.222.333/0001-81"


# ---- CEP ----

class TestCep:
    def test_cep_valido(self):
        assert is_valid_cep("01310100") is True
        assert is_valid_cep("01310-100") is True

    def test_cep_invalido(self):
        assert is_valid_cep("123") is False
        assert is_valid_cep("xxxx") is False
        assert is_valid_cep(None) is False

    def test_normalize_cep(self):
        assert normalize_cep("01310-100") == "01310100"
        assert normalize_cep("invalido") is None

    def test_format_cep(self):
        assert format_cep("01310100") == "01310-100"


# ---- UF ----

class TestUf:
    def test_uf_valido(self):
        assert is_valid_uf("SP") is True
        assert is_valid_uf("sp") is True  # case-insensitive
        assert is_valid_uf("MS") is True

    def test_uf_invalido(self):
        assert is_valid_uf("XX") is False
        assert is_valid_uf("") is False
        assert is_valid_uf(None) is False
        assert is_valid_uf("S") is False


# ---- only_digits helper ----

class TestOnlyDigits:
    def test_strip_mascaras(self):
        assert only_digits("123.456.789-09") == "12345678909"
        assert only_digits("(11) 99999-9999") == "11999999999"
        assert only_digits("") == ""
        assert only_digits(None) == ""
