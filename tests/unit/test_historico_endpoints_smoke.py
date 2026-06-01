"""Smoke do módulo Histórico (`/api/historico`) — TestClient sem DB (roda em CI).

Valida que cada endpoint existe e exige service token (401 sem auth).
"""

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_listar_historico_sem_auth_401(self) -> None:
        assert _client().get("/api/historico").status_code == 401

    def test_export_historico_sem_auth_401(self) -> None:
        assert _client().get("/api/historico/export?formato=csv").status_code == 401

    def test_detalhe_historico_sem_auth_401(self) -> None:
        assert _client().get("/api/historico/1").status_code == 401

    def test_export_formato_invalido_exige_auth_primeiro(self) -> None:
        # Sem token, o gateway de auth responde antes da validação de formato.
        assert _client().get("/api/historico/export?formato=pdf").status_code == 401


class TestSmokeRelatorios:
    def test_resumo_sem_auth_401(self) -> None:
        assert _client().get("/api/historico/relatorios/resumo").status_code == 401

    def test_por_operador_sem_auth_401(self) -> None:
        assert (
            _client().get("/api/historico/relatorios/por-operador").status_code == 401
        )

    def test_por_departamento_sem_auth_401(self) -> None:
        assert (
            _client().get("/api/historico/relatorios/por-departamento").status_code
            == 401
        )

    def test_por_canal_sem_auth_401(self) -> None:
        assert _client().get("/api/historico/relatorios/por-canal").status_code == 401
