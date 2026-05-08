"""MediaExtractionValidator — verifica que worker pré-processou a mídia
e injetou o resultado em `message_queue.normalized_input` com prefixo
correto (`[Descrição de imagem]:`, `[Transcrição de áudio]:`,
`[Conteúdo do documento (mime)]:`).

Determinístico via string match. Valida:
- modalidade='texto': normalized_input = body original
- modalidade='imagem': contém `[Descrição de imagem]:`
- modalidade='audio': contém `[Transcrição de áudio]:`
- modalidade='pdf': contém `[Conteúdo do documento`
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    name: str
    passed: bool
    razao: str
    detalhes: dict


_PREFIXO_POR_MODALIDADE = {
    "texto": None,  # texto puro: normalized_input = body
    "imagem": "[Descrição de imagem]",
    "audio": "[Transcrição de áudio]",
    "pdf": "[Conteúdo do documento",
}


class MediaExtractionValidator:
    """Valida que mídia foi pré-processada e prefixo apropriado está presente."""

    name = "MediaExtractionValidator"

    def __init__(self, modalidade: str):
        if modalidade not in _PREFIXO_POR_MODALIDADE:
            raise ValueError(f"modalidade inválida: {modalidade!r}")
        self.modalidade = modalidade

    def measure(self, jornada) -> ValidationResult:
        ni = jornada.normalized_input_modalidade or ""

        if self.modalidade == "texto":
            # Pra texto, basta `normalized_input` ser não-vazio
            if len(ni.strip()) < 3:
                return ValidationResult(
                    name=self.name,
                    passed=False,
                    razao="normalized_input vazio pra texto",
                    detalhes={"normalized_input": ni[:200]},
                )
            return ValidationResult(
                name=self.name,
                passed=True,
                razao="texto preservado em normalized_input",
                detalhes={"normalized_input": ni[:200]},
            )

        prefixo = _PREFIXO_POR_MODALIDADE[self.modalidade]
        if not prefixo or prefixo not in ni:
            return ValidationResult(
                name=self.name,
                passed=False,
                razao=(
                    f"normalized_input não contém prefixo '{prefixo}' "
                    f"esperado pra modalidade {self.modalidade}"
                ),
                detalhes={"normalized_input": ni[:300]},
            )

        # Bonus: confere que a parte extraída tem conteúdo (>20 chars após prefixo)
        idx = ni.find(prefixo)
        depois = ni[idx + len(prefixo):][:200].strip()
        if len(depois) < 20:
            return ValidationResult(
                name=self.name,
                passed=False,
                razao=(
                    f"prefixo presente mas conteúdo extraído muito curto "
                    f"({len(depois)} chars)"
                ),
                detalhes={"normalized_input": ni[:300]},
            )

        return ValidationResult(
            name=self.name,
            passed=True,
            razao=f"mídia processada e prefixo '{prefixo}' presente",
            detalhes={
                "normalized_input": ni[:300],
                "prefixo_pos": idx,
            },
        )
