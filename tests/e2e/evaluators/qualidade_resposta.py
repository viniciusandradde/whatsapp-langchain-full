"""G-Eval (DeepEval) com LLM judge — qualidade da resposta do agente.

Sprint K.3 — wrapper sobre OpenRouter pra usar `google/gemini-2.5-flash-lite`
(mesmo modelo barato do router atual). Custo ~$0.000005 por chamada.

Pra desabilitar em runs locais (CI sem OPENROUTER_API_KEY): env
`SKIP_DEEPEVAL=1`. Usa stub leve quando deepeval não está instalado.
"""

from __future__ import annotations

import os
from typing import Any


def _get_openrouter_llm():
    """Cria DeepEvalBaseLLM apontando pra OpenRouter (compatível OpenAI).

    DeepEval suporta provider custom via subclasse de DeepEvalBaseLLM.
    Aqui usamos `openai` SDK direto (já dependência transitiva) com
    base_url=https://openrouter.ai/api/v1.
    """
    from deepeval.models.base_model import DeepEvalBaseLLM
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY ausente — configure pra rodar G-Eval."
        )

    model_name = os.getenv("DEEPEVAL_MODEL", "google/gemini-2.5-flash-lite")

    class OpenRouterLLM(DeepEvalBaseLLM):
        def __init__(self):
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )

        def load_model(self) -> Any:
            return self.client

        def generate(self, prompt: str) -> str:
            r = self.client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            return r.choices[0].message.content or ""

        async def a_generate(self, prompt: str) -> str:
            return self.generate(prompt)

        def get_model_name(self) -> str:
            return model_name

    return OpenRouterLLM()


def avaliar_qualidade_resposta(jornada, setor: dict, modalidade: str) -> dict:
    """Roda G-Eval com critério custom em pt-BR sobre a resposta do agente.

    Retorna dict com score (0-1), threshold, razao, raw_geval_output.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase

    # DeepEval 3.x renomeou: usa SingleTurnParams. Fallback pra LLMTestCaseParams
    # em versões antigas via try/except dinâmico.
    try:
        from deepeval.test_case import SingleTurnParams as TurnParams  # type: ignore
    except ImportError:
        from deepeval.test_case import LLMTestCaseParams as TurnParams  # type: ignore

    llm = _get_openrouter_llm()

    contexto = (
        f"Cliente foi direcionado pelo menu pra setor '{setor['slug']}'. "
        f"Modalidade do turno final: {modalidade}. "
        f"Atendimento ID #{jornada.atendimento_id}. "
    )
    output_agente = (
        jornada.response_proativa or jornada.response_final or ""
    )

    test_case = LLMTestCase(
        input=f"Cliente entrou via setor {setor['slug']} ({modalidade})",
        actual_output=output_agente or "[sem resposta]",
        context=[contexto],
    )

    metric = GEval(
        name="QualidadeRespostaAgente",
        criteria=(
            "Avalie a resposta do agente IA (actual_output) considerando: "
            "(a) Cumprimentou em português brasileiro? "
            "(b) Identificou ou se apresentou como o setor correto? "
            "(c) Pediu informações relevantes pra triagem (nome, demanda, etc)? "
            "(d) NÃO inventou dados que não foram fornecidos pelo cliente? "
            "(e) Tom acolhedor e profissional? "
            "Retorne score alto (>0.8) só se TODOS os critérios forem atendidos. "
            "Score 0.5-0.8 se alguns falharem mas resposta é razoável. "
            "Score baixo (<0.5) se resposta é vazia, em outro idioma ou inventa dados."
        ),
        evaluation_params=[
            TurnParams.INPUT,  # type: ignore[attr-defined]
            TurnParams.ACTUAL_OUTPUT,  # type: ignore[attr-defined]
            TurnParams.CONTEXT,  # type: ignore[attr-defined]
        ],
        threshold=0.7,
        model=llm,
    )

    metric.measure(test_case)
    return {
        "score": float(metric.score or 0.0),
        "threshold": metric.threshold,
        "razao": metric.reason or "",
        "passed": (metric.score or 0.0) >= metric.threshold,
        "modelo_judge": llm.get_model_name(),
    }
