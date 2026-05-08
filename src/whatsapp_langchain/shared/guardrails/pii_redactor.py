"""PII Redactor — Sprint O.2.

Mascara CPF, CNPJ, email, telefone, cartão antes de enviar pra LLM (input)
e antes de mandar resposta pra cliente (output).

Determinístico, ~10-30ms pra texto de 1KB. Não usa NLP/spaCy (evita custo).

Exemplos:
    "meu cpf é 123.456.789-09" → "meu cpf é ***.***.***-**"
    "email teste@x.com"        → "email ***@***"
    "(11) 98765-4321"          → "(**) *****-****"
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Regex compilados — chamado em todo input/output
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_PHONE_BR_RE = re.compile(
    r"(?:\+?55\s*)?\(?\d{2}\)?\s*9?\s*\d{4,5}[-\s]?\d{4}"
)
_CARD_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")


@dataclass(frozen=True)
class PIIRedactResult:
    text: str
    counts: dict[str, int]  # tipo → quantidade redacted

    @property
    def redacted_anything(self) -> bool:
        return sum(self.counts.values()) > 0


def redact_pii(text: str, *, mode: str = "mask") -> PIIRedactResult:
    """Redaction de PII no texto.

    mode:
      "mask": substitui por asteriscos preservando formato
      "block": substitui por placeholder genérico [PII]
      "remove": remove completamente
    """
    if not text:
        return PIIRedactResult(text=text or "", counts={})

    counts: dict[str, int] = {
        "cpf": 0, "cnpj": 0, "email": 0, "phone": 0, "card": 0
    }

    def _replace_cpf(m: re.Match) -> str:
        counts["cpf"] += 1
        if mode == "mask":
            return "***.***.***-**"
        return "[CPF]" if mode == "block" else ""

    def _replace_cnpj(m: re.Match) -> str:
        counts["cnpj"] += 1
        if mode == "mask":
            return "**.***.***/****-**"
        return "[CNPJ]" if mode == "block" else ""

    def _replace_email(m: re.Match) -> str:
        counts["email"] += 1
        if mode == "mask":
            local, _, domain = m.group(0).partition("@")
            return f"{local[0]}***@***.{domain.split('.')[-1]}"
        return "[EMAIL]" if mode == "block" else ""

    def _replace_phone(m: re.Match) -> str:
        counts["phone"] += 1
        if mode == "mask":
            return "(**) *****-****"
        return "[PHONE]" if mode == "block" else ""

    def _replace_card(m: re.Match) -> str:
        counts["card"] += 1
        if mode == "mask":
            return "**** **** **** ****"
        return "[CARD]" if mode == "block" else ""

    text = _CARD_RE.sub(_replace_card, text)        # card antes de phone (overlap)
    text = _CNPJ_RE.sub(_replace_cnpj, text)        # CNPJ antes de CPF (mais específico)
    text = _CPF_RE.sub(_replace_cpf, text)
    text = _EMAIL_RE.sub(_replace_email, text)
    text = _PHONE_BR_RE.sub(_replace_phone, text)

    return PIIRedactResult(text=text, counts=counts)


def has_pii(text: str) -> bool:
    """Helper rápido pra detectar (sem redact). Útil pra log/skip."""
    if not text:
        return False
    return bool(
        _CPF_RE.search(text) or _CNPJ_RE.search(text)
        or _EMAIL_RE.search(text) or _PHONE_BR_RE.search(text)
        or _CARD_RE.search(text)
    )
