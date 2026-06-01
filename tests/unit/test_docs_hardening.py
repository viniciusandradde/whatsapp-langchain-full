"""Smoke: hardening dos docs/OpenAPI.

Cobre as 2 brechas fechadas:
1. Docs/OpenAPI gateados em produção (404 sem token; 200 com service token via
   query `?token=` ou header Bearer). Abertos em dev.
2. OpenAPI declara `securitySchemes.ServiceToken` (bearer) e marca as rotas
   admin com `security` — rotas públicas (ex. /health) ficam sem.

TestClient sem `with` → não dispara lifespan/DB (roda em CI).
"""

from fastapi.testclient import TestClient

from whatsapp_langchain.shared.config import settings

_TOKEN = "test-service-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # >= 32 chars


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestDocsOpenInDev:
    def test_docs_200_in_dev(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "development")
        r = _client().get("/docs")
        assert r.status_code == 200
        assert "swagger" in r.text.lower()

    def test_openapi_200_in_dev(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "development")
        assert _client().get("/openapi.json").status_code == 200


class TestDocsGatedInProd:
    def test_docs_404_without_token(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        assert _client().get("/docs").status_code == 404

    def test_openapi_404_without_token(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        assert _client().get("/openapi.json").status_code == 404

    def test_docs_200_with_query_token(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "internal_service_token", _TOKEN)
        assert _client().get(f"/docs?token={_TOKEN}").status_code == 200

    def test_openapi_200_with_bearer(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "internal_service_token", _TOKEN)
        r = _client().get(
            "/openapi.json", headers={"Authorization": f"Bearer {_TOKEN}"}
        )
        assert r.status_code == 200

    def test_docs_404_with_wrong_token(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "internal_service_token", _TOKEN)
        assert _client().get("/docs?token=errado").status_code == 404


class TestSecurityScheme:
    def _spec(self, monkeypatch) -> dict:
        monkeypatch.setattr(settings, "environment", "development")
        return _client().get("/openapi.json").json()

    def test_service_token_scheme_declared(self, monkeypatch):
        schemes = (
            self._spec(monkeypatch).get("components", {}).get("securitySchemes", {})
        )
        assert "ServiceToken" in schemes
        assert schemes["ServiceToken"]["type"] == "http"
        assert schemes["ServiceToken"]["scheme"] == "bearer"

    def test_admin_route_marked_secure(self, monkeypatch):
        spec = self._spec(monkeypatch)
        secured_api = [
            path
            for path, item in spec["paths"].items()
            if path.startswith("/api/")
            for method in item.values()
            if isinstance(method, dict)
            and any("ServiceToken" in req for req in method.get("security", []))
        ]
        assert secured_api, "nenhuma rota /api/* ficou com security ServiceToken"

    def test_public_route_not_secured(self, monkeypatch):
        spec = self._spec(monkeypatch)
        # /health é público — não deve exigir ServiceToken
        get = spec["paths"].get("/health", {}).get("get", {})
        assert not get.get("security")
