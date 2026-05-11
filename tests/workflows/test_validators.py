"""Testes dos validators de `ask_text` (MVP #9).

Reusa `shared/validators_br.py` via `workflows/validators.py::validate_input`.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.workflows.validators import validate_input


@pytest.mark.parametrize(
    "text, rule, expected_ok",
    [
        # CPF
        ("11144477735", "cpf", True),  # válido (dígitos calculados)
        ("12345678901", "cpf", False),
        ("", "cpf", False),
        # CNPJ
        ("11222333000181", "cnpj", True),  # válido
        ("11111111111111", "cnpj", False),
        # CEP
        ("12345-678", "cep", True),
        ("12345678", "cep", True),
        ("123", "cep", False),
        # UF
        ("SP", "uf", True),
        ("ms", "uf", True),
        ("XX", "uf", False),
        # data_br
        ("15/03/2025", "data_br", True),
        ("32/13/2025", "data_br", False),
        # telefone_br
        ("11987654321", "telefone_br", True),
        ("1198765", "telefone_br", False),
        # email
        ("foo@bar.com", "email", True),
        ("not-an-email", "email", False),
        # min_len:N
        ("Maria", "min_len:3", True),
        ("Jo", "min_len:3", False),
        # max_len:N
        ("oi", "max_len:5", True),
        ("texto bem longo", "max_len:5", False),
        # regex
        ("12345", "regex:^[0-9]+$", True),
        ("12abc", "regex:^[0-9]+$", False),
        # rule None → sempre OK
        ("qualquer", None, True),
        # rule desconhecida → aceita silenciosamente
        ("foo", "rule_inexistente", True),
    ],
)
def test_validate_input(text, rule, expected_ok):
    ok, err = validate_input(text, rule)
    assert ok == expected_ok, f"text={text!r} rule={rule!r} ok={ok} err={err!r}"
    if not ok:
        assert err, "esperava mensagem de erro quando ok=False"


def test_validate_input_dict_form():
    """Forma dict combina múltiplas regras (AND)."""
    ok, _ = validate_input("João", {"min_len": 2})
    assert ok is True

    ok, err = validate_input("A", {"min_len": 2})
    assert ok is False
    assert "2" in err
