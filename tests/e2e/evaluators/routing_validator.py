"""RoutingValidator — verifica que o atendimento foi atribuído ao
agente_ia correto + departamento_id esperado após escolha do menu.

Determinístico, sem LLM. Mede contra DB direto.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    name: str
    passed: bool
    razao: str
    detalhes: dict


class RoutingValidator:
    """Valida que após a escolha do menu, atendimento.agente_atual e
    departamento_id estão setados corretamente.

    `depto_esperado=None` significa que o agente não tem dep_default
    configurado (caso `atendimento-cliente` no nosso setup) — aí
    `departamento_id` deve ficar NULL.
    """

    def __init__(self, *, agente_esperado: str, depto_esperado: int | None):
        self.agente_esperado = agente_esperado
        self.depto_esperado = depto_esperado
        self.name = "RoutingValidator"

    def measure(self, jornada) -> ValidationResult:
        if jornada.agente_atual != self.agente_esperado:
            return ValidationResult(
                name=self.name,
                passed=False,
                razao=(
                    f"agente_atual='{jornada.agente_atual}' "
                    f"esperado '{self.agente_esperado}'"
                ),
                detalhes=jornada.to_dict(),
            )
        if jornada.departamento_id != self.depto_esperado:
            return ValidationResult(
                name=self.name,
                passed=False,
                razao=(
                    f"departamento_id={jornada.departamento_id} "
                    f"esperado {self.depto_esperado}"
                ),
                detalhes=jornada.to_dict(),
            )
        return ValidationResult(
            name=self.name,
            passed=True,
            razao="agente_atual e departamento_id corretos",
            detalhes={
                "agente_atual": jornada.agente_atual,
                "departamento_id": jornada.departamento_id,
            },
        )
