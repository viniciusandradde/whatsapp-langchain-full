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


# Cumprimentos + indicadores de "agente em modo triagem ativa" — lenient.
# Inclui:
#   - Cumprimentos formais (olá, oi, bom dia, sou, equipe)
#   - Perguntas de triagem (qual seu, me conte, posso ajudar)
#   - Reconhecimento de mídia (vi/recebi/observei/identifiquei)
#   - Convites pra continuar (o que você precisa, em que posso)
# Validar isto = agente respondeu em pt-BR e iniciou interação adequada.
# Falha quando: silêncio, resposta em outro idioma, "I cannot help".
_REGEX_CUMPRIMENTO = re.compile(
    r"\b(ol[áa]|oi|bom dia|boa tarde|boa noite|sou|equipe|"
    r"posso ajudar|como posso|estou aqui|claro|qual seu|qual o|"
    r"qual \w+|me conte|me diga|por favor|gostaria|"
    r"para te ajudar|para que eu possa|seja bem-?vind[oa]|"
    r"vi |recebi|observei|identifiquei|notei|detectei|"
    r"o que você precisa|em que posso|o que posso|"
    r"você gostaria|me explica|me passa|pode me|me orienta|"
    r"que dúvida|qual sua dúvida|qual a dúvida|"
    # Reconhecimento de conteúdo da mídia (áudio/imagem/PDF)
    r"entendi|entendo|certo|perfeito|ok|"
    r"li |analisei|conferi|verifiquei|consegui ver|"
    r"vamos lá|tudo bem|tranquilo|sem problema|"
    r"compreendi|peguei|anotado|"
    # Disposição pra continuar
    r"\\bà disposição|\\baqui pra (te |você )?ajudar|"
    r"posso (te )?(orientar|esclarecer|auxiliar|atender)|"
    r"se precisar|qualquer (coisa|dúvida)|"
    r"fico (aqui|à disposição))\b",
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
