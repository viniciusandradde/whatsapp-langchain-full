"""Validadores brasileiros — CPF, CNPJ, CEP. (Fase 1.A)

Foco: validação algorítmica (dígitos verificadores) + normalização
(strip de máscara). Sem chamadas externas (Receita/ViaCEP) — essas
ficam pra worker dedicado se virar requisito.
"""

from __future__ import annotations


def only_digits(s: str | None) -> str:
    """Remove tudo que não é dígito. None → ''."""
    if not s:
        return ""
    return "".join(c for c in s if c.isdigit())


# ---- CPF ----


def is_valid_cpf(cpf: str | None) -> bool:
    """Valida CPF via dígito verificador (DV).

    Aceita formatado ('123.456.789-09') ou só dígitos. False pra:
    - String vazia/None
    - Tamanho != 11 dígitos
    - Sequências repetidas (000.., 111.., ..., 999..)
    - DV inválido
    """
    digits = only_digits(cpf)
    if len(digits) != 11:
        return False
    # Sequência repetida — comum em geradores fake
    if digits == digits[0] * 11:
        return False

    # Calcula primeiro DV
    soma = sum(int(digits[i]) * (10 - i) for i in range(9))
    dv1 = (soma * 10) % 11
    if dv1 == 10:
        dv1 = 0
    if dv1 != int(digits[9]):
        return False

    # Calcula segundo DV
    soma = sum(int(digits[i]) * (11 - i) for i in range(10))
    dv2 = (soma * 10) % 11
    if dv2 == 10:
        dv2 = 0
    return dv2 == int(digits[10])


def normalize_cpf(cpf: str | None) -> str | None:
    """Retorna CPF só com dígitos OU None se inválido."""
    digits = only_digits(cpf)
    if not digits:
        return None
    return digits if is_valid_cpf(digits) else None


def format_cpf(cpf: str | None) -> str:
    """Formata pra '123.456.789-09' (UI)."""
    d = only_digits(cpf)
    if len(d) != 11:
        return cpf or ""
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


# ---- CNPJ ----


def is_valid_cnpj(cnpj: str | None) -> bool:
    """Valida CNPJ via DV. Aceita formatado ou só dígitos."""
    digits = only_digits(cnpj)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False

    # Pesos pro primeiro DV: 5,4,3,2,9,8,7,6,5,4,3,2
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digits[i]) * pesos1[i] for i in range(12))
    dv1 = soma % 11
    dv1 = 0 if dv1 < 2 else 11 - dv1
    if dv1 != int(digits[12]):
        return False

    # Pesos pro segundo DV: 6,5,4,3,2,9,8,7,6,5,4,3,2
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(digits[i]) * pesos2[i] for i in range(13))
    dv2 = soma % 11
    dv2 = 0 if dv2 < 2 else 11 - dv2
    return dv2 == int(digits[13])


def normalize_cnpj(cnpj: str | None) -> str | None:
    digits = only_digits(cnpj)
    if not digits:
        return None
    return digits if is_valid_cnpj(digits) else None


def format_cnpj(cnpj: str | None) -> str:
    """Formata pra '12.345.678/0001-90' (UI)."""
    d = only_digits(cnpj)
    if len(d) != 14:
        return cnpj or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


# ---- CEP ----


def is_valid_cep(cep: str | None) -> bool:
    """CEP é 8 dígitos. Não valida se a faixa existe."""
    return len(only_digits(cep)) == 8


def normalize_cep(cep: str | None) -> str | None:
    digits = only_digits(cep)
    if len(digits) != 8:
        return None
    return digits


def format_cep(cep: str | None) -> str:
    """Formata pra '01310-100' (UI)."""
    d = only_digits(cep)
    if len(d) != 8:
        return cep or ""
    return f"{d[:5]}-{d[5:]}"


# ---- UF ----

VALID_UFS: frozenset[str] = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
        "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
        "RS", "RO", "RR", "SC", "SP", "SE", "TO",
    }
)


def is_valid_uf(uf: str | None) -> bool:
    if not uf:
        return False
    return uf.upper() in VALID_UFS
