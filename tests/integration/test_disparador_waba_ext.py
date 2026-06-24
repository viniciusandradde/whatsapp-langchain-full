"""Smoke + E2E dos endpoints WABA da extensão (canal oficial roteado pelo backend).

Endpoints: GET /api/disparador/ext/conexoes, GET /api/disparador/ext/templates,
POST /api/disparador/ext/campanha-template. Autenticados por API key por empresa
(scopes dispatch/templates).

Smoke (CI, sem DB):
    uv run pytest tests/integration/test_disparador_waba_ext.py::TestSmoke -v

E2E (stack rodando, migrações 118/093/034 aplicadas):
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_disparador_waba_ext.py::TestE2E -v -s
"""

from __future__ import annotations

import json
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.shared.api_key import generate_api_key

from .helpers import API_BASE_URL, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rotas registradas e exigindo API key (401 sem credencial)."""

    def test_conexoes_sem_auth_401(self) -> None:
        assert _client().get("/api/disparador/ext/conexoes").status_code == 401

    def test_templates_sem_auth_401(self) -> None:
        # conexao_id presente pra passar da validação de query e chegar no auth.
        r = _client().get("/api/disparador/ext/templates?conexao_id=1")
        assert r.status_code == 401, r.text

    def test_campanha_template_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/disparador/ext/campanha-template",
            json={
                "nome": "x",
                "conexao_id": 1,
                "message_template_id": 1,
                "telefones": ["5511999990001"],
            },
        )
        assert r.status_code == 401, r.text


_RUN = uuid.uuid4().hex[:8]


@pytest.mark.docker_demo
class TestE2E:
    """Empresa + conexão WABA + template aprovado → lista e cria campanha."""

    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"wabaext-{_RUN}", f"wabaext-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    @pytest.fixture(scope="class")
    def conexao_id(self, empresa) -> int:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number, display_name, status)
                VALUES (%s, 'waba', %s, %s, 'active') RETURNING id
                """,
                (empresa, f"+55119{_RUN[:7]}", f"WABA {_RUN}"),
            ).fetchone()
            assert row is not None
            return row[0]

    @pytest.fixture(scope="class")
    def template_id(self, empresa, conexao_id) -> int:
        comp = json.dumps([{"type": "BODY", "text": "Olá {{1}}! Tudo bem?"}])
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                """
                INSERT INTO waba_template
                    (empresa_id, conexao_id, nome, categoria, idioma,
                     componentes_json, status, provider)
                VALUES (%s, %s, %s, 'MARKETING', 'pt_BR', %s, 'approved', 'waba')
                RETURNING id
                """,
                (empresa, conexao_id, f"tpl_{_RUN}", comp),
            ).fetchone()
            assert row is not None
            return row[0]

    def _key(self, empresa_id: int, scopes: list[str]) -> str:
        plain, prefix, key_hash = generate_api_key(empresa_id)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                """
                INSERT INTO empresa_api_key
                    (empresa_id, label, key_prefix, key_hash, scopes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (empresa_id, f"e2e-{prefix}", prefix, key_hash, scopes),
            )
        return plain

    def _h(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}"}

    def test_01_lista_conexoes(self, empresa, conexao_id) -> None:
        key = self._key(empresa, ["dispatch", "templates"])
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/ext/conexoes",
            headers=self._h(key),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        ids = [c["id"] for c in r.json()["items"]]
        assert conexao_id in ids, r.text
        item = next(c for c in r.json()["items"] if c["id"] == conexao_id)
        assert item["provider"] == "waba"

    def test_02_lista_templates_com_variaveis(
        self, empresa, conexao_id, template_id
    ) -> None:
        key = self._key(empresa, ["dispatch", "templates"])
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/ext/templates",
            params={"conexao_id": conexao_id},
            headers=self._h(key),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        tpl = next((t for t in items if t["id"] == template_id), None)
        assert tpl is not None, r.text
        assert tpl["variaveis"] == ["1"], tpl

    def test_03_cria_campanha_template(self, empresa, conexao_id, template_id) -> None:
        key = self._key(empresa, ["dispatch", "templates"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/campanha-template",
            headers=self._h(key),
            json={
                "nome": f"E2E WABA {_RUN}",
                "conexao_id": conexao_id,
                "message_template_id": template_id,
                "template_variaveis": {"1": "João"},
                "telefones": ["5511999990001", "5511999990002"],
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        camp_id = r.json()["campanha_id"]
        assert r.json()["agendada"] is False
        # persistiu com template + conexão certos
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT empresa_id, conexao_id, message_template_id "
                "FROM campanha WHERE id = %s",
                (camp_id,),
            ).fetchone()
        assert row == (empresa, conexao_id, template_id), row

    def test_04_agendamento_marca_agendada(
        self, empresa, conexao_id, template_id
    ) -> None:
        key = self._key(empresa, ["dispatch", "templates"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/campanha-template",
            headers=self._h(key),
            json={
                "nome": f"E2E WABA agendada {_RUN}",
                "conexao_id": conexao_id,
                "message_template_id": template_id,
                "telefones": ["5511999990003"],
                "scheduled_at": "2099-01-01T10:00:00+00:00",
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        assert r.json()["agendada"] is True

    def test_05_scope_insuficiente_403(self, empresa, conexao_id) -> None:
        # chave só com 'capture' não pode listar conexões (exige dispatch).
        key = self._key(empresa, ["capture"])
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/ext/conexoes",
            headers=self._h(key),
            timeout=10,
        )
        assert r.status_code == 403, r.text
