"""Testes dos endpoints CRUD /api/base-conhecimento (M5.c)."""

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
from whatsapp_langchain.shared.models import DocumentoConhecimento


def _doc(**overrides) -> DocumentoConhecimento:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "titulo": "Política de Trocas",
        "conteudo": "7 dias.",
        "tags": [],
        "ativo": True,
        "created_by_user_id": "user-x",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return DocumentoConhecimento(**base)


@pytest.fixture
def client():
    """TestClient com auth desabilitada e empresa_id=1, user=user-x."""
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_documentos(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.list_documentos",
        new=AsyncMock(return_value=[_doc(), _doc(id=2, titulo="FAQ Pagamento")]),
    ):
        response = client.get("/api/base-conhecimento")
    assert response.status_code == 200
    data = response.json()
    assert len(data["documentos"]) == 2


def test_get_documento_returns_doc(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.get_documento",
        new=AsyncMock(return_value=_doc(id=10, titulo="X")),
    ):
        response = client.get("/api/base-conhecimento/10")
    assert response.status_code == 200
    assert response.json()["titulo"] == "X"


def test_get_documento_404_when_missing(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.get_documento",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/base-conhecimento/99")
    assert response.status_code == 404


def test_create_documento_returns_201(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.upsert_documento",
        new=AsyncMock(return_value=_doc(id=42)),
    ) as mock_upsert:
        response = client.post(
            "/api/base-conhecimento",
            json={"titulo": "Novo", "conteudo": "conteudo aqui", "tags": ["faq"]},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42
    kwargs = mock_upsert.await_args.kwargs
    assert kwargs == {"user_id": "user-x"}


def test_create_documento_422_on_empty_titulo(client):
    response = client.post(
        "/api/base-conhecimento", json={"titulo": "", "conteudo": "y"}
    )
    assert response.status_code == 422


def test_update_documento_returns_200(client):
    with (
        patch(
            "whatsapp_langchain.shared.base_conhecimento.get_documento",
            new=AsyncMock(return_value=_doc()),
        ),
        patch(
            "whatsapp_langchain.shared.base_conhecimento.upsert_documento",
            new=AsyncMock(return_value=_doc(titulo="Atualizado")),
        ),
    ):
        response = client.put(
            "/api/base-conhecimento/1",
            json={"titulo": "Atualizado", "conteudo": "novo"},
        )
    assert response.status_code == 200
    assert response.json()["titulo"] == "Atualizado"


def test_update_documento_404_when_missing(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.get_documento",
        new=AsyncMock(return_value=None),
    ):
        response = client.put(
            "/api/base-conhecimento/99",
            json={"titulo": "x", "conteudo": "y"},
        )
    assert response.status_code == 404


def test_delete_documento_returns_204(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.delete_documento",
        new=AsyncMock(return_value=True),
    ):
        response = client.delete("/api/base-conhecimento/1")
    assert response.status_code == 204


def test_delete_documento_404_when_missing(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.delete_documento",
        new=AsyncMock(return_value=False),
    ):
        response = client.delete("/api/base-conhecimento/99")
    assert response.status_code == 404


def test_buscar_documentos_returns_search_results(client):
    from whatsapp_langchain.shared.base_conhecimento import SearchResult

    result = SearchResult(
        documento=_doc(id=1, titulo="A"),
        chunk_idx=0,
        chunk_conteudo="trecho relevante",
        score=0.85,
        reason="bate exato",
    )
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.search_relevant",
        new=AsyncMock(return_value=[result]),
    ) as mock_search:
        response = client.post(
            "/api/base-conhecimento/buscar", json={"query": "trocas"}
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["resultados"]) == 1
    r = data["resultados"][0]
    assert r["score"] == pytest.approx(0.85)
    assert r["chunk_idx"] == 0
    assert r["chunk_conteudo"] == "trecho relevante"
    assert r["reason"] == "bate exato"
    assert r["documento"]["titulo"] == "A"
    kwargs = mock_search.await_args.kwargs
    assert kwargs == {"k": 3, "rerank": True}


def test_buscar_validates_query(client):
    response = client.post("/api/base-conhecimento/buscar", json={"query": ""})
    assert response.status_code == 422


def test_routes_require_service_token():
    """Sem override de verify_service_token, request retorna 401/403."""
    # Limpa overrides pra forçar verificação real
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/api/base-conhecimento")
    assert response.status_code in (401, 403)


# --- M5.c.2: upload ---


def test_upload_creates_documento_from_txt(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.upsert_documento",
        new=AsyncMock(return_value=_doc(id=99, titulo="manual")),
    ) as mock_upsert:
        response = client.post(
            "/api/base-conhecimento/upload",
            files={"arquivo": ("manual.txt", b"Conteudo do manual", "text/plain")},
            data={"tags": "faq,manual"},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 99
    # upsert_documento foi chamado com titulo derivado do filename
    body = mock_upsert.await_args.args[2]
    assert body.titulo == "manual"
    assert body.tags == ["faq", "manual"]
    assert "Conteudo do manual" in body.conteudo


def test_upload_uses_explicit_titulo_when_provided(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.upsert_documento",
        new=AsyncMock(return_value=_doc()),
    ) as mock_upsert:
        response = client.post(
            "/api/base-conhecimento/upload",
            files={"arquivo": ("doc.txt", b"texto", "text/plain")},
            data={"titulo": "Manual Operacional"},
        )
    assert response.status_code == 201
    body = mock_upsert.await_args.args[2]
    assert body.titulo == "Manual Operacional"


def test_upload_415_on_unsupported_extension(client):
    """M5.c.3: png passou a ser aceito; mp4 ainda não."""
    response = client.post(
        "/api/base-conhecimento/upload",
        files={"arquivo": ("video.mp4", b"fake mp4", "video/mp4")},
    )
    assert response.status_code == 415


def test_upload_422_on_empty_file(client):
    response = client.post(
        "/api/base-conhecimento/upload",
        files={"arquivo": ("vazio.txt", b"", "text/plain")},
    )
    assert response.status_code == 422


def test_upload_413_when_too_large(client):
    huge = b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/base-conhecimento/upload",
        files={"arquivo": ("big.txt", huge, "text/plain")},
    )
    assert response.status_code == 413


def test_upload_filters_empty_tags(client):
    with patch(
        "whatsapp_langchain.shared.base_conhecimento.upsert_documento",
        new=AsyncMock(return_value=_doc()),
    ) as mock_upsert:
        client.post(
            "/api/base-conhecimento/upload",
            files={"arquivo": ("a.txt", b"x", "text/plain")},
            data={"tags": "manual,,  ,faq"},
        )
    body = mock_upsert.await_args.args[2]
    assert body.tags == ["manual", "faq"]
