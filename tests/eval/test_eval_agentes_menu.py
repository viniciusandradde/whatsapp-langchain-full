"""Sprint Eval-UI — roda `evaluate_agentes` como pytest parametrized,
expondo no painel `/relatorios/allure` via subprocess.

Env vars controladas pelo runner (`tests_runner/runner.py`):
- EVAL_SOURCE: "local" | "langsmith" (default "local")
- EVAL_PER_AGENT: int (default 3)
- EVAL_PASS_THRESHOLD: float (default 0.5)

Cada agente vira 1 teste parametrizado. Allure recebe steps + attachments
(JSON detalhado por exemplo). Falha se overall_continuous < threshold.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import allure
import pytest

# Importa o helper diretamente do script (não é pacote instalado).
_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from eval_agentes_menu import evaluate_agentes  # noqa: E402

AGENTES = [
    "agendamentos",
    "atendimento",
    "atendimento-cliente",
    "exames",
    "orcamento",
    "ouvidoria",
]

PER_AGENT = int(os.environ.get("EVAL_PER_AGENT", "3"))
SOURCE = os.environ.get("EVAL_SOURCE", "local")
PASS_THRESHOLD = float(os.environ.get("EVAL_PASS_THRESHOLD", "0.5"))


@pytest.mark.docker_demo
@pytest.mark.asyncio
@pytest.mark.parametrize("agente_slug", AGENTES)
async def test_eval_agente(agente_slug: str) -> None:
    """Roda eval contra `agente_slug` e valida `overall_continuous >= threshold`.

    Em falha, o Allure mostra:
    - summary com totais
    - 1 attachment JSON por exemplo com cliente_msg / expected / actual /
      score_continuous / reason_continuous (pt-BR)
    """
    allure.dynamic.title(f"Eval NPS judge — {agente_slug}")
    allure.dynamic.feature("eval-agentes-menu")
    allure.dynamic.story(f"source={SOURCE}")
    allure.dynamic.label("agente", agente_slug)
    allure.dynamic.parameter("source", SOURCE)
    allure.dynamic.parameter("per_agent", PER_AGENT)
    allure.dynamic.parameter("pass_threshold", PASS_THRESHOLD)

    with allure.step(f"Roda eval de {PER_AGENT} exemplos do agente {agente_slug}"):
        result = await evaluate_agentes(
            source=SOURCE,
            per_agent=PER_AGENT,
            filter_agente=agente_slug,
            verbose=False,
        )

    overall = result.get("overall_continuous")
    total = result.get("total", 0)

    summary = (
        f"agente: {agente_slug}\n"
        f"source: {SOURCE}\n"
        f"total avaliados: {total}\n"
        f"overall_continuous: {overall if overall is None else f'{overall:.3f}'}\n"
        f"pass_threshold: {PASS_THRESHOLD}\n"
    )
    allure.attach(
        summary,
        name="summary",
        attachment_type=allure.attachment_type.TEXT,
    )

    for r in result.get("results", []):
        sc = r.get("score_continuous")
        label = (
            f"ex-{r.get('fewshot_id', '?')}-score-{sc:.2f}"
            if sc is not None
            else f"ex-{r.get('fewshot_id', '?')}-fail"
        )
        allure.attach(
            json.dumps(r, ensure_ascii=False, indent=2),
            name=label,
            attachment_type=allure.attachment_type.JSON,
        )

    assert total > 0, (
        f"Nenhum exemplo amostrado pra {agente_slug} "
        f"(source={SOURCE}, per_agent={PER_AGENT})"
    )
    assert overall is not None, f"overall_continuous é None pra {agente_slug}"
    assert overall >= PASS_THRESHOLD, (
        f"NPS continuous {overall:.3f} < {PASS_THRESHOLD} pro agente {agente_slug}"
    )
