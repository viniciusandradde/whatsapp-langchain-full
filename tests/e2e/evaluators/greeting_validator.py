"""GreetingValidator — checa se o agente IA cumprimentou em pt-BR
ao iniciar a triagem (resposta proativa após [NOVO_ATENDIMENTO_TRIAGEM]).

Rule-based via regex — determinístico, 0 custo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    name: str
    passed: bool
    razao: str
    detalhes: dict


# Cumprimentos pt-BR comuns + indicadores de "agente apresentando-se"
_REGEX_CUMPRIMENTO = re.compile(
    r"\b(ol[áa]|oi|bom dia|boa tarde|boa noite|sou|equipe|posso ajudar|"
    r"como posso|estou aqui)\b",
    re.IGNORECASE,
)


class GreetingValidator:
    """Valida cumprimento + apresentação na resposta proativa do agente."""

    name = "GreetingValidator"

    def measure(self, jornada) -> ValidationResult:
        # Resposta proativa é a do agente após menu (sentinel
        # [NOVO_ATENDIMENTO_TRIAGEM]). Se ausente, fallback pra response_final
        # do turno 3 (alguns agentes podem cumprimentar lá em vez de proativo).
        candidato = (jornada.response_proativa or jornada.response_final or "").strip()
        if not candidato:
            return ValidationResult(
                name=self.name,
                passed=False,
                razao="sem resposta proativa nem final do agente",
                detalhes={"response_proativa": None, "response_final": None},
            )
        if not _REGEX_CUMPRIMENTO.search(candidato):
            return ValidationResult(
                name=self.name,
                passed=False,
                razao=(
                    "resposta não tem cumprimento pt-BR ("
                    "olá/oi/bom dia/boa tarde/sou/equipe/posso ajudar)"
                ),
                detalhes={"resposta": candidato[:300]},
            )
        return ValidationResult(
            name=self.name,
            passed=True,
            razao="agente cumprimentou em pt-BR",
            detalhes={"resposta": candidato[:300]},
        )
