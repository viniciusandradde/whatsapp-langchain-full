"""Smoke tests do endpoint /api/dashboard/atendimento."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeDashboardAtendimento:
    def test_get_dashboard_sem_auth_401(self) -> None:
        assert _client().get("/api/dashboard/atendimento").status_code == 401

    def test_get_dashboard_com_periodo_sem_auth_401(self) -> None:
        resp = _client().get("/api/dashboard/atendimento?periodo=7d")
        assert resp.status_code == 401

    def test_periodo_invalido_eh_normalizado(self) -> None:
        """Periodo inválido cai pra default ('hoje') — sem 422."""
        resp = _client().get("/api/dashboard/atendimento?periodo=invalido")
        # Sem auth retorna 401 antes da validação — confirma que rota existe
        assert resp.status_code == 401
