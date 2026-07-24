"""Smoke dos endpoints Fase 1 (auto-dataset Langfuse + eval)."""

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_from_langfuse_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/admin/rag/dataset/from-langfuse", json={"min_score": 8}
        )
        assert r.status_code == 401

    def test_eval_run_sem_auth_401(self) -> None:
        r = _client().post("/api/admin/rag/eval/run", json={"per_agent": 3})
        assert r.status_code == 401
