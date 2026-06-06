"""Guardrails — Sprint O (smart guards condicional).

4 camadas:
- input_filter: detecta prompt injection / jailbreak antes do LLM
- pii_redactor: mascara dados sensíveis (CPF, email, tel) input + output
- hitl: human-in-the-loop em ações irreversíveis (transfer, cancelar)
- output_judge: LLM-as-judge anti-hallucination (condicional, não sempre)

Estratégia: O.1+O.2 sempre ativos (~25ms), O.3 só dispara em tools sensíveis,
O.4 só roda quando RAG fraco + resposta tem fatos verificáveis.
"""

from whatsapp_langchain.shared.guardrails.input_filter import (
    InputFilterResult,
    check_input,
)
from whatsapp_langchain.shared.guardrails.pii_redactor import (
    PIIRedactResult,
    redact_pii,
)

__all__ = [
    "check_input",
    "InputFilterResult",
    "redact_pii",
    "PIIRedactResult",
]
