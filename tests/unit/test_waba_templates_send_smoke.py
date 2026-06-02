"""Smoke — envio de template (composer) + campanha com template.

Sem service token o gateway nega (401). Valida que os endpoints novos da
sprint "WABA templates utilizáveis" existem e exigem auth. Roda em CI (sem DB).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeWabaTemplateSend:
    def test_atendimento_send_template_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/atendimentos/1/send-template", json={"template_id": 1}
        )
        assert r.status_code == 401, r.text

    def test_campanha_create_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/campanhas",
            json={"nome": "x", "telefones": ["+5511999999999"],
                  "message_template_id": 1},
        )
        assert r.status_code == 401, r.text
