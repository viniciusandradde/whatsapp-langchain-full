"""Smoke tests dos endpoints de workflows estilo state-machine.

Branch: proposta/menu-langgraph-workflows.

Valida que as 5 rotas existem + exigem token de serviço (sem auth → 401).
CRUD completo precisa fixture DB + empresa + permissões — não tentamos.

Nota: não usamos `with TestClient(app)` (context manager) pra evitar
disparar o `lifespan` que tenta conectar no DB. Pra teste de 401, o
middleware de auth bate ANTES de qualquer acesso ao banco.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from whatsapp_langchain.server.main import app

    return TestClient(app)


def test_list_workflows_sem_auth_retorna_401():
    resp = _client().get("/api/admin/workflows")
    assert resp.status_code == 401


def test_get_workflow_byid_sem_auth_retorna_401():
    resp = _client().get("/api/admin/workflows/1")
    assert resp.status_code == 401


def test_put_workflow_sem_auth_retorna_401():
    resp = _client().put(
        "/api/admin/workflows/1",
        json={"nome": "X"},
    )
    assert resp.status_code == 401


def test_toggle_workflow_sem_auth_retorna_401():
    resp = _client().post("/api/admin/workflows/1/toggle-active")
    assert resp.status_code == 401


def test_workflow_state_sem_auth_retorna_401():
    resp = _client().get("/api/admin/atendimentos/1/workflow-state")
    assert resp.status_code == 401
