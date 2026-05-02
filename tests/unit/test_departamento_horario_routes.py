"""Testes dos endpoints de Departamento, Horário e Feriado (M6.a)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import (
    Departamento,
    Feriado,
    HorarioFuncionamento,
)


@pytest.fixture
def client():
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _dep(**overrides) -> Departamento:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "nome": "Suporte",
        "descricao": None,
        "ativo": True,
        "created_by_user_id": "user-x",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Departamento(**base)


def _hor(**overrides) -> HorarioFuncionamento:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "dia_semana": 1,
        "hora_inicio": "09:00",
        "hora_fim": "18:00",
        "departamento_id": None,
        "ativo": True,
        "created_at": now,
    }
    base.update(overrides)
    return HorarioFuncionamento(**base)


def _fer(**overrides) -> Feriado:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "data": "2026-12-25",
        "descricao": "Natal",
        "created_by_user_id": "user-x",
        "created_at": now,
    }
    base.update(overrides)
    return Feriado(**base)


# --- Departamento ---


def test_list_departamentos(client):
    with patch(
        "whatsapp_langchain.server.routes.departamento.list_departamentos",
        new=AsyncMock(return_value=[_dep(), _dep(id=2, nome="Vendas")]),
    ):
        response = client.get("/api/departamentos")
    assert response.status_code == 200
    assert len(response.json()["departamentos"]) == 2


def test_create_departamento_returns_201(client):
    with patch(
        "whatsapp_langchain.server.routes.departamento.create_departamento",
        new=AsyncMock(return_value=_dep(id=42)),
    ):
        response = client.post(
            "/api/departamentos", json={"nome": "Suporte"}
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42


def test_create_departamento_409_on_duplicate(client):
    from whatsapp_langchain.shared.departamento import DuplicateDepartamentoError

    with patch(
        "whatsapp_langchain.server.routes.departamento.create_departamento",
        new=AsyncMock(side_effect=DuplicateDepartamentoError("já existe")),
    ):
        response = client.post(
            "/api/departamentos", json={"nome": "Suporte"}
        )
    assert response.status_code == 409


def test_delete_departamento_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.departamento.delete_departamento",
        new=AsyncMock(return_value=False),
    ):
        response = client.delete("/api/departamentos/99")
    assert response.status_code == 404


# --- Horarios ---


def test_list_horarios(client):
    with patch(
        "whatsapp_langchain.server.routes.horario.list_all_horarios",
        new=AsyncMock(return_value=[_hor(), _hor(id=2, dia_semana=2)]),
    ):
        response = client.get("/api/horarios")
    assert response.status_code == 200
    assert len(response.json()["horarios"]) == 2


def test_create_horario_returns_201(client):
    with patch(
        "whatsapp_langchain.server.routes.horario.create_horario",
        new=AsyncMock(return_value=_hor(id=10)),
    ):
        response = client.post(
            "/api/horarios",
            json={"dia_semana": 1, "hora_inicio": "09:00", "hora_fim": "18:00"},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 10


def test_create_horario_422_when_fim_before_inicio(client):
    response = client.post(
        "/api/horarios",
        json={"dia_semana": 1, "hora_inicio": "18:00", "hora_fim": "09:00"},
    )
    assert response.status_code == 422


def test_create_horario_422_on_invalid_time_format(client):
    response = client.post(
        "/api/horarios",
        json={"dia_semana": 1, "hora_inicio": "9", "hora_fim": "18"},
    )
    assert response.status_code == 422


def test_horarios_status_returns_is_open(client):
    with patch(
        "whatsapp_langchain.server.routes.horario.is_business_hours",
        new=AsyncMock(return_value=True),
    ):
        response = client.get("/api/horarios/status")
    assert response.status_code == 200
    assert response.json() == {"is_open": True}


# --- Feriados ---


def test_list_feriados(client):
    with patch(
        "whatsapp_langchain.server.routes.horario.list_feriados",
        new=AsyncMock(return_value=[_fer()]),
    ):
        response = client.get("/api/feriados")
    assert response.status_code == 200
    assert len(response.json()["feriados"]) == 1


def test_create_feriado_returns_201(client):
    with patch(
        "whatsapp_langchain.server.routes.horario.create_feriado",
        new=AsyncMock(return_value=_fer(id=10)),
    ):
        response = client.post(
            "/api/feriados",
            json={"data": "2026-12-25", "descricao": "Natal"},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 10


def test_create_feriado_409_on_duplicate(client):
    from whatsapp_langchain.shared.horario import DuplicateFeriadoError

    with patch(
        "whatsapp_langchain.server.routes.horario.create_feriado",
        new=AsyncMock(side_effect=DuplicateFeriadoError("já existe")),
    ):
        response = client.post(
            "/api/feriados", json={"data": "2026-12-25"}
        )
    assert response.status_code == 409


def test_create_feriado_422_on_invalid_date(client):
    response = client.post(
        "/api/feriados", json={"data": "25/12/2026"}
    )
    assert response.status_code == 422


def test_routes_require_service_token():
    app.dependency_overrides.clear()
    client = TestClient(app)
    for path in ("/api/departamentos", "/api/horarios", "/api/feriados"):
        response = client.get(path)
        assert response.status_code in (401, 403), path
