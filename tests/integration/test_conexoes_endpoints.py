"""Smoke + E2E dos endpoints de conexões (Sprint Conexões WABA/Evolution).

Smoke (sem DB): valida que todas as 18 rotas (11 conexão + 7 template) exigem
service token. Roda em CI.

E2E (com stack rodando): bloqueado nesta sprint — exige Meta App real ou
Evolution server real pros fluxos completos. Marcadores `docker_demo` em
sprint futura quando tivermos mocks server-side.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeConexoesCRUD:
    """5 endpoints CRUD + 1 legacy test-evolution."""

    def test_list_conexoes_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes").status_code == 401

    def test_get_conexao_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1").status_code == 401

    def test_create_conexao_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes",
            json={"provider": "twilio_sandbox", "from_number": "+5511999"},
        )
        assert resp.status_code == 401

    def test_patch_conexao_sem_auth_401(self) -> None:
        resp = _client().patch("/api/conexoes/1", json={"display_name": "X"})
        assert resp.status_code == 401

    def test_delete_conexao_sem_auth_401(self) -> None:
        assert _client().delete("/api/conexoes/1").status_code == 401

    def test_test_evolution_legacy_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/test-evolution",
            json={"api_url": "https://x", "api_key": "k", "instance_name": "i"},
        )
        assert resp.status_code == 401


class TestSmokeConexoesWABAOAuth:
    """3 endpoints OAuth Embedded Signup."""

    def test_waba_oauth_start_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/waba/oauth/start", json={"display_name": "X"}
        )
        assert resp.status_code == 401

    def test_waba_oauth_result_sem_auth_401(self) -> None:
        resp = _client().get("/api/conexoes/waba/oauth/result?state=xx")
        assert resp.status_code == 401

    def test_waba_finalize_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/waba/finalize",
            json={
                "state": "x",
                "waba_account_id": "a",
                "phone_id": "p",
                "display_name": "X",
            },
        )
        assert resp.status_code == 401


class TestSmokeConexoesEvolution:
    """3 endpoints Evolution + QR + status."""

    def test_evolution_provision_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/evolution/provision",
            json={"display_name": "X"},
        )
        assert resp.status_code == 401

    def test_get_qr_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1/qr").status_code == 401

    def test_get_status_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1/status").status_code == 401


class TestSmokeConexoesOps:
    """3 endpoints ops: test, disconnect."""

    def test_test_conexao_sem_auth_401(self) -> None:
        assert _client().post("/api/conexoes/1/test").status_code == 401

    def test_disconnect_sem_auth_401(self) -> None:
        assert _client().post("/api/conexoes/1/disconnect").status_code == 401


class TestSmokeWABATemplates:
    """7 endpoints templates."""

    def test_list_templates_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1/templates").status_code == 401

    def test_create_template_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/1/templates",
            json={
                "nome": "x",
                "categoria": "UTILITY",
                "idioma": "pt_BR",
                "componentes_json": [],
            },
        )
        assert resp.status_code == 401

    def test_get_template_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1/templates/1").status_code == 401

    def test_sync_template_sem_auth_401(self) -> None:
        assert _client().post("/api/conexoes/1/templates/1/sync").status_code == 401

    def test_test_send_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/conexoes/1/templates/1/test-send",
            json={"to_number": "+5511", "variables": {}},
        )
        assert resp.status_code == 401

    def test_delete_template_sem_auth_401(self) -> None:
        assert _client().delete("/api/conexoes/1/templates/1").status_code == 401

    def test_import_sem_auth_401(self) -> None:
        assert _client().post("/api/conexoes/1/templates/import").status_code == 401


class TestSmokeWebhookWABA:
    """Webhook não exige service token (Meta envia, não nosso front)."""

    def test_get_webhook_sem_token_falha_400_ou_403(self) -> None:
        """Sem hub.mode, retorna 400."""
        resp = _client().get("/webhook/waba")
        assert resp.status_code in (400, 403)

    def test_get_webhook_verify_token_invalido_403(self) -> None:
        resp = _client().get(
            "/webhook/waba?hub.mode=subscribe"
            "&hub.verify_token=invalid&hub.challenge=test"
        )
        assert resp.status_code == 403

    def test_post_webhook_aceita_payload_vazio_200(self) -> None:
        """POST sem assinatura/payload válido retorna 200 (Meta retenta forte
        em qualquer outra coisa). Log warning interno."""
        resp = _client().post("/webhook/waba", json={"object": "page"})
        assert resp.status_code == 200
