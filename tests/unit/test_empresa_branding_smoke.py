"""Smoke — white-label da empresa (logo + cores).

Sem service token o gateway nega (401). Roda em CI (sem DB).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeEmpresaBranding:
    def test_upload_logo_sem_auth_401(self) -> None:
        assert _client().post("/api/empresas/1/logo").status_code == 401

    def test_update_cor_sem_auth_401(self) -> None:
        r = _client().put("/api/empresas/1", json={"cor_primaria": "#ff0000"})
        assert r.status_code == 401

    def test_uploads_logos_mount_existe(self) -> None:
        # StaticFiles mount montado: arquivo inexistente → 404 (não 405/erro
        # de rota), provando que o mount /uploads/logos está registrado.
        assert _client().get("/uploads/logos/nope.png").status_code == 404
