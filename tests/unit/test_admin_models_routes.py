"""Testes dos endpoints administrativos de configuração de modelos LLM."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.main import app


@pytest.fixture
def client():
    """TestClient com auth desabilitada e empresa_id=1 fixo no contexto.

    Pra testes de routing/lógica, override de dependencies é mais limpo
    do que injetar headers manualmente em cada chamada.
    """
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _mock_pool(*fetchone_results):
    """Constrói mock de pool psycopg cujo fetchone() retorna cada item em sequência."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=list(fetchone_results))
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def test_list_models_returns_curated_list(client):
    """GET /api/models retorna a lista curada do shared/llm.py."""
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()

    assert "models" in data
    assert isinstance(data["models"], list)
    assert len(data["models"]) > 0

    ids = [m["id"] for m in data["models"]]
    assert "openai/gpt-4o-mini" in ids
    assert "google/gemini-2.5-flash-lite" in ids
    types = {m["type"] for m in data["models"]}
    assert {"chat", "media"}.issubset(types)


def test_get_agent_config_falls_back_to_env(client, monkeypatch):
    """Sem row em agent_llm_config → resolved == settings.openrouter_*."""
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_midia_model",
        "env-midia",
    )

    pool, _ = _mock_pool(None)
    with patch(
        "whatsapp_langchain.server.routes.admin.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        response = client.get("/api/agents/vsa_tech/config")

    assert response.status_code == 200
    assert response.json() == {
        "agent_id": "vsa_tech",
        "chat_model": "env-chat",
        "midia_model": "env-midia",
        "chat_model_override": None,
        "midia_model_override": None,
    }


def test_put_agent_config_persists_and_returns_updated(client, monkeypatch):
    """PUT aplica os overrides e o response reflete os valores recém-salvos."""
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_midia_model",
        "env-midia",
    )

    # 1ª fetchone (após o INSERT, dentro do get_agent_config interno).
    pool, conn = _mock_pool(("openai/gpt-4o-mini", "google/gemini-2.5-flash-lite"))

    with patch(
        "whatsapp_langchain.server.routes.admin.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        response = client.put(
            "/api/agents/vsa_tech/config",
            json={
                "chat_model": "openai/gpt-4o-mini",
                "midia_model": "google/gemini-2.5-flash-lite",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["chat_model"] == "openai/gpt-4o-mini"
    assert data["midia_model"] == "google/gemini-2.5-flash-lite"
    assert data["chat_model_override"] == "openai/gpt-4o-mini"
    assert data["midia_model_override"] == "google/gemini-2.5-flash-lite"

    # Confirma que o INSERT ON CONFLICT foi executado com os valores corretos.
    insert_calls = [
        call for call in conn.execute.await_args_list if "INSERT" in str(call.args[0])
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[1] == (
        1,
        "vsa_tech",
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash-lite",
    )


def test_put_agent_config_clears_override_with_empty_string(client, monkeypatch):
    """String vazia ou None vira NULL no DB (volta a usar env)."""
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.server.routes.admin.settings.openrouter_midia_model",
        "env-midia",
    )

    pool, conn = _mock_pool((None, None))

    with patch(
        "whatsapp_langchain.server.routes.admin.get_pool",
        new=AsyncMock(return_value=pool),
    ):
        response = client.put(
            "/api/agents/vsa_tech/config",
            json={"chat_model": "", "midia_model": None},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["chat_model_override"] is None
    assert data["midia_model_override"] is None
    # No DB foi gravado None pra ambos
    insert_calls = [
        call for call in conn.execute.await_args_list if "INSERT" in str(call.args[0])
    ]
    assert insert_calls[0].args[1] == (1, "vsa_tech", None, None)


def test_get_agent_config_returns_400_for_unknown_agent(client, monkeypatch):
    """Agent inexistente → 400 via AgentNotFoundError handler do main.py."""
    response = client.get("/api/agents/nao_existe/config")
    assert response.status_code == 400
    assert "nao_existe" in response.json()["detail"]
