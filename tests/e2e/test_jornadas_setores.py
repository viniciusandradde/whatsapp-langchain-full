"""Bateria E2E — 7 setores × 4 modalidades = 28 cenários.

Sprint K — valida fluxo completo do cliente desde menu welcome até a
resposta do agente_ia processando mídia. Cada cenário gera dados
verificáveis pelo painel admin (`/atendimento`).

Padrão herdado de `tests/integration/test_realistic_flows.py`:
- marker `docker_demo` (precisa stack rodando)
- helpers de `tests/integration/helpers.py`
- fixtures de `tests/e2e/conftest.py`

Para rodar:
    make test-e2e

Para rodar 1 cenário específico:
    uv run pytest tests/e2e/test_jornadas_setores.py -v -s \\
      -k "agendamentos and pdf"
"""

from __future__ import annotations

import json
import os

import allure
import pytest

from tests.e2e.conftest import MODALIDADES, SETORES
from tests.e2e.evaluators.greeting_validator import GreetingValidator
from tests.e2e.evaluators.media_extraction_validator import (
    MediaExtractionValidator,
)
from tests.e2e.evaluators.routing_validator import RoutingValidator
from tests.e2e.fixtures.jornada import simular_jornada_setor

pytestmark = pytest.mark.docker_demo


@pytest.mark.parametrize("setor", SETORES, ids=[s["slug"] for s in SETORES])
@pytest.mark.parametrize("modalidade", MODALIDADES)
class TestJornadasMultiSetor:
    """28 cenários: cada setor × cada modalidade.

    Cada teste:
    1. Cliente novo → menu welcome → escolhe setor → recebe
       transferência + posição + agente proativo
    2. Cliente envia mensagem (texto OU mídia) → agente processa
    3. 3 validators rule-based: routing, greeting, media extraction
    4. (Opcional) G-Eval LLM judge se DEEPEVAL_MODEL setado
    """

    def test_jornada_setor_modalidade(
        self,
        setor: dict,
        modalidade: str,
        db_url: str,
        media_server_urls: dict,
    ) -> None:
        allure.dynamic.title(f"{setor['slug']} / {modalidade}")
        allure.dynamic.label("setor", setor["slug"])
        allure.dynamic.label("modalidade", modalidade)

        with allure.step("Simular jornada (3 turnos: oi → opcao → mensagem)"):
            jornada = simular_jornada_setor(
                setor, modalidade, media_server_urls, db_url
            )
            allure.attach(
                json.dumps(jornada.to_dict(), indent=2, ensure_ascii=False),
                name="jornada-snapshot.json",
                attachment_type=allure.attachment_type.JSON,
            )
            if jornada.erros:
                pytest.fail(f"Jornada falhou: {jornada.erros}")

        allure.dynamic.parameter("latencia_total_s", jornada.latencia_total_s)
        allure.dynamic.parameter("phone", jornada.phone)
        allure.dynamic.parameter("atendimento_id", jornada.atendimento_id)

        # Validator 1 — Routing (agente correto + depto correto)
        with allure.step("RoutingValidator"):
            v = RoutingValidator(
                agente_esperado=setor["agente"],
                depto_esperado=setor["depto"],
            )
            r = v.measure(jornada)
            allure.attach(
                json.dumps(r.detalhes, indent=2, ensure_ascii=False),
                name="routing-detalhes.json",
                attachment_type=allure.attachment_type.JSON,
            )
            assert r.passed, f"[Routing] {r.razao}"

        # Validator 2 — Greeting (cumprimento pt-BR do agente)
        with allure.step("GreetingValidator"):
            v = GreetingValidator()
            r = v.measure(jornada)
            allure.attach(
                json.dumps(r.detalhes, indent=2, ensure_ascii=False),
                name="greeting-detalhes.json",
                attachment_type=allure.attachment_type.JSON,
            )
            assert r.passed, f"[Greeting] {r.razao}"

        # Validator 3 — MediaExtraction (worker pré-processou mídia)
        with allure.step("MediaExtractionValidator"):
            v = MediaExtractionValidator(modalidade=modalidade)
            r = v.measure(jornada)
            allure.attach(
                json.dumps(r.detalhes, indent=2, ensure_ascii=False),
                name="media-extraction-detalhes.json",
                attachment_type=allure.attachment_type.JSON,
            )
            assert r.passed, f"[MediaExtraction] {r.razao}"

        # Validator 4 (opcional) — G-Eval LLM judge
        if not os.getenv("SKIP_DEEPEVAL"):
            with allure.step("G-Eval QualidadeRespostaAgente (LLM judge)"):
                try:
                    from tests.e2e.evaluators.qualidade_resposta import (
                        avaliar_qualidade_resposta,
                    )

                    score = avaliar_qualidade_resposta(jornada, setor, modalidade)
                    allure.attach(
                        json.dumps(score, indent=2, ensure_ascii=False),
                        name="g-eval-score.json",
                        attachment_type=allure.attachment_type.JSON,
                    )
                    if score["score"] < score["threshold"]:
                        pytest.fail(
                            f"[QualidadeRespostaAgente] score "
                            f"{score['score']:.2f} < threshold "
                            f"{score['threshold']:.2f}: {score['razao']}"
                        )
                except ImportError:
                    allure.attach(
                        "DeepEval não instalado — skip",
                        name="g-eval-skip.txt",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                except Exception as exc:
                    # G-Eval externo (LLM judge) não deve quebrar o teste
                    # se rule-based validators passaram. Só anexa o erro.
                    allure.attach(
                        f"G-Eval falhou (não bloqueante): {exc}",
                        name="g-eval-error.txt",
                        attachment_type=allure.attachment_type.TEXT,
                    )
