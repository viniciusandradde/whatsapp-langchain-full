"""Smoke dos endpoints de voz do agente (mig 176).

Padrão de `test_aba_endpoints.py`: TestClient sem DB — valida que a rota
existe e exige auth (401 sem service token). Roda em CI.

Para rodar:
    uv run pytest tests/integration/test_voz_endpoints.py::TestSmoke -v
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Verifica que as rotas estão registradas e exigem auth."""

    def test_preview_voz_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/empresas/1/voz/preview",
            json={"voz_nome": "coral", "voz_estilo": ""},
        )
        assert resp.status_code == 401

    def test_preview_voz_rota_registrada(self) -> None:
        """404 aqui = alguém removeu a rota; o 401 acima já prova, mas este
        teste falha com mensagem melhor quando a rota some."""
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/empresas/{empresa_id}/voz/preview" in rotas
