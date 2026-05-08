"""Input filter — detecta prompt injection / jailbreak (Sprint O.1).

Determinístico, ~5ms. Lista de patterns PT-BR + EN cobrindo:
- Jailbreak clássico ("ignore all previous", "DAN mode", etc)
- Tentativas de extrair system prompt
- Instruções de override ("you are now...", "agora você é...")
- Pedidos de ação ilícita disfarçados
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


# Patterns de jailbreak / prompt injection.
# Mantém compilados pra performance (chamado por toda mensagem que chega).
_PATTERNS_RAW: list[tuple[str, str]] = [
    # Jailbreak EN
    ("jailbreak_en", r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|rules?)"),
    ("jailbreak_en2", r"\b(DAN|do\s*anything\s*now|jailbroken)\b"),
    ("override_en", r"\byou\s+are\s+(now|actually)\s+(an?\s+)?(unrestricted|uncensored|no\s+restrictions)"),
    ("system_extract_en", r"\b(reveal|show|tell\s+me|print|output)\s+(your|the)\s+(system\s+)?(prompt|instructions|rules)\b"),

    # Jailbreak PT-BR
    ("jailbreak_pt", r"\b(ignore|esque[çc]a|desconsidere)\s+(tudo|todas?|as)\s+(instru[çc][õo]es|regras|prompts?)"),
    ("override_pt", r"\b(agora|a\s+partir\s+de\s+agora)\s+voc[êe]\s+[ée]\s+"),
    ("system_extract_pt", r"\b(mostre?|revele?|imprima)\s+(seu|o)\s+(prompt|instru[çc][õo]es|sistema)"),
    ("role_swap_pt", r"\b(finja|simule|assuma)\s+(que|ser)\s+"),

    # Pedidos diretos de violação
    ("desconto_ilicito", r"\b(me\s+d[êe]|d[êe]\s+me)\s+(\d+\s*%?\s*)?desconto\s+(de\s+)?(\d+\s*%|gr[áa]tis|grand[ée])"),
    ("acesso_admin", r"\b(modo\s+(admin|administrador|root|developer)|sudo)\b"),

    # Code injection
    ("code_inject", r"<\s*script\s*>|javascript:|on\w+\s*="),
    ("sql_inject", r"\b(DROP|DELETE|TRUNCATE)\s+(TABLE|FROM|DATABASE)\b", ),
]

_COMPILED = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in _PATTERNS_RAW]


@dataclass(frozen=True)
class InputFilterResult:
    blocked: bool
    pattern: str | None
    sample: str | None  # primeiros 100 chars onde casou


def check_input(text: str) -> InputFilterResult:
    """Verifica se input do cliente bate em algum pattern proibido.

    Performance: ~5ms pra texto de 200 chars com 11 patterns.
    """
    if not text or not text.strip():
        return InputFilterResult(blocked=False, pattern=None, sample=None)

    for name, regex in _COMPILED:
        m = regex.search(text)
        if m:
            sample = text[max(0, m.start() - 20): m.end() + 20]
            logger.warning(
                "guardrail_input_blocked",
                pattern=name,
                sample=sample[:100],
            )
            return InputFilterResult(
                blocked=True, pattern=name, sample=sample[:100]
            )
    return InputFilterResult(blocked=False, pattern=None, sample=None)


def is_safe(text: str) -> bool:
    """Helper: True se input passa nos guardrails."""
    return not check_input(text).blocked
