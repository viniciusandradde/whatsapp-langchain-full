"""Validators usados nos nodes `ask_text` e `validate`.

Sprint Workflow-LangGraph MVP #9 — reusa `shared/validators_br.py` em vez
de reimplementar regras BR.

Spec do `validate_with`:
- `"cpf"` / `"cnpj"` / `"cep"` / `"uf"` — validators_br
- `"data_br"` — data dd/mm/aaaa
- `"telefone_br"` — telefone BR (10-11 dígitos)
- `"email"` — pattern simples
- `"min_len:N"` — mín N caracteres
- `"max_len:N"` — máx N caracteres
- `"regex:..."` — regex literal
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from whatsapp_langchain.shared import validators_br


def _is_valid_data_br(text: str) -> bool:
    """Data dd/mm/aaaa (separadores `/`, `-` ou `.`)."""
    if not text:
        return False
    cleaned = re.sub(r"[/\-.]", "/", text.strip())
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            datetime.strptime(cleaned, fmt)
            return True
        except ValueError:
            continue
    return False


def _is_valid_telefone_br(text: str) -> bool:
    """Telefone BR: 10 ou 11 dígitos (DDD + número)."""
    digits = re.sub(r"\D", "", text or "")
    return 10 <= len(digits) <= 11


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _is_valid_email(text: str) -> bool:
    return bool(_EMAIL_RE.fullmatch((text or "").strip()))


# Validators simples (1 argumento: text)
_SIMPLE_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "cpf": validators_br.is_valid_cpf,
    "cnpj": validators_br.is_valid_cnpj,
    "cep": validators_br.is_valid_cep,
    "uf": validators_br.is_valid_uf,
    "data_br": _is_valid_data_br,
    "telefone_br": _is_valid_telefone_br,
    "email": _is_valid_email,
}


_DEFAULT_ERROR_MESSAGES: dict[str, str] = {
    "cpf": "CPF inválido. Digite os 11 dígitos.",
    "cnpj": "CNPJ inválido. Digite os 14 dígitos.",
    "cep": "CEP inválido. Use o formato 00000-000.",
    "uf": "UF inválida. Use a sigla de 2 letras (ex: SP, MS, RJ).",
    "data_br": "Data inválida. Use dd/mm/aaaa.",
    "telefone_br": "Telefone inválido. Use DDD + número.",
    "email": "E-mail inválido.",
}


def validate_input(text: str | None, rule: str | dict | None) -> tuple[bool, str]:
    """Valida `text` contra `rule`.

    Args:
        text: input do cliente
        rule: pode ser:
          - None → sempre OK
          - str simples: "cpf", "data_br", "min_len:3", "regex:^[0-9]+$"
          - dict: {"min_len": 3, "regex": "..."} (várias regras AND)

    Returns:
        (ok, error_message)
    """
    if not rule:
        return True, ""
    text = (text or "").strip()
    if isinstance(rule, str):
        return _apply_rule_str(text, rule)
    if isinstance(rule, dict):
        for k, v in rule.items():
            ok, err = _apply_rule_str(text, f"{k}:{v}" if v is not True else k)
            if not ok:
                return False, err
        return True, ""
    return True, ""


def _apply_rule_str(text: str, rule: str) -> tuple[bool, str]:
    """Parse string `kind` ou `kind:param` e aplica."""
    if ":" in rule:
        kind, _, param = rule.partition(":")
    else:
        kind, param = rule, ""
    kind = kind.strip()
    param = param.strip()

    if kind in _SIMPLE_VALIDATORS:
        ok = _SIMPLE_VALIDATORS[kind](text)
        return ok, "" if ok else _DEFAULT_ERROR_MESSAGES.get(kind, "Inválido.")

    if kind == "min_len":
        try:
            n = int(param)
        except ValueError:
            return False, "Configuração min_len inválida."
        if len(text) < n:
            return False, f"Mínimo {n} caracteres."
        return True, ""

    if kind == "max_len":
        try:
            n = int(param)
        except ValueError:
            return False, "Configuração max_len inválida."
        if len(text) > n:
            return False, f"Máximo {n} caracteres."
        return True, ""

    if kind == "regex":
        try:
            if re.fullmatch(param, text):
                return True, ""
            return False, "Formato inválido."
        except re.error:
            return False, "Regex inválida (config)."

    # rule desconhecida → aceita silenciosamente (avoiding false negatives)
    return True, ""
