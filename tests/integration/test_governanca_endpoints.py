"""Smoke tests dos endpoints de Governança RBAC (Sprint mig 083+084).

Valida que rotas existem + exigem service token. CRUD completo precisa
fixture DB — não tentamos.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from whatsapp_langchain.server.main import app

    return TestClient(app)


def test_get_member_perfis_sem_auth_401():
    resp = _client().get("/api/empresas/1/membros/abc/perfis")
    assert resp.status_code == 401


def test_put_member_perfis_sem_auth_401():
    resp = _client().put(
        "/api/empresas/1/membros/abc/perfis", json={"perfil_ids": [1]}
    )
    assert resp.status_code == 401


def test_get_member_departamentos_sem_auth_401():
    resp = _client().get("/api/empresas/1/membros/abc/departamentos")
    assert resp.status_code == 401


def test_put_member_departamentos_sem_auth_401():
    resp = _client().put(
        "/api/empresas/1/membros/abc/departamentos",
        json={"departamento_ids": [1]},
    )
    assert resp.status_code == 401


def test_audit_governanca_sem_auth_401():
    resp = _client().get("/api/empresas/1/audit/governanca")
    assert resp.status_code == 401
