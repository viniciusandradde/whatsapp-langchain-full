"""Smoke do módulo Teste de Agente (chat no painel sem WhatsApp).

Valida registro da rota + exigência de auth. O comportamento real
(pipeline load_graph) é validado manualmente via painel — o handler abre
checkpointer/store reais, inviável em unit test sem stack.
"""

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_testar_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar", json={"mensagem": "oi"}
        )
        assert resp.status_code == 401

    def test_testar_reset_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar",
            json={"mensagem": "", "resetar": True},
        )
        assert resp.status_code == 401


class TestSmokeBateria:
    def test_bateria_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar-bateria",
            json={"modelos": ["google/gemini-2.5-flash"]},
        )
        assert resp.status_code == 401

    def test_testar_com_modelo_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar",
            json={"mensagem": "oi", "modelo": "gpt-4o-mini"},
        )
        assert resp.status_code == 401
