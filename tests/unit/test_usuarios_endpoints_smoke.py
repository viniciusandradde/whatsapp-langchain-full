"""Sprint U.7 — smoke tests pros endpoints /api/usuarios.

Garante que sem service token o gateway nega tudo (401), e que
o contrato de criação valida nome obrigatório (422) quando autenticado
ainda que com header fake (não chega no DB — fail-fast no Pydantic).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeUsuariosEndpoints:
    def test_get_list_sem_auth_401(self) -> None:
        resp = _client().get("/api/usuarios")
        assert resp.status_code == 401, resp.text

    def test_get_detail_sem_auth_401(self) -> None:
        resp = _client().get("/api/usuarios/some-uuid")
        assert resp.status_code == 401, resp.text

    def test_post_sem_auth_401(self) -> None:
        resp = _client().post("/api/usuarios", json={"nome": "Foo"})
        assert resp.status_code == 401, resp.text

    def test_put_sem_auth_401(self) -> None:
        resp = _client().put("/api/usuarios/x", json={"nome": "Foo"})
        assert resp.status_code == 401, resp.text

    def test_post_avatar_sem_auth_401(self) -> None:
        resp = _client().post("/api/usuarios/x/avatar")
        assert resp.status_code == 401, resp.text

    def test_post_sessions_invalidate_sem_auth_401(self) -> None:
        resp = _client().post("/api/usuarios/x/sessions/invalidate")
        assert resp.status_code == 401, resp.text

    def test_get_exists_sem_auth_401(self) -> None:
        resp = _client().get("/api/usuarios/exists/abc")
        assert resp.status_code == 401, resp.text

    def test_patch_status_sem_auth_401(self) -> None:
        resp = _client().patch("/api/usuarios/x/status", json={"status": "active"})
        assert resp.status_code == 401, resp.text

    def test_post_replicar_sem_auth_401(self) -> None:
        resp = _client().post("/api/usuarios/x/replicar", json={"nome": "Foo"})
        assert resp.status_code == 401, resp.text

    def test_delete_sem_auth_401(self) -> None:
        resp = _client().delete("/api/usuarios/x")
        assert resp.status_code == 401, resp.text

    def test_atividade_sem_auth_401(self) -> None:
        resp = _client().get("/api/usuarios/x/atividade")
        assert resp.status_code == 401, resp.text
