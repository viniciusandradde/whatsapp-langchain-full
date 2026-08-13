"""Smoke + E2E do interruptor "IA continua na fila" (mig 166).

Smoke (sem DB): rotas existem e exigem service token. Roda em CI.
E2E (stack real): criar → default desligado → ligar → ler de volta → isolamento.

    uv run pytest tests/integration/test_departamento_ia_na_fila.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_departamento_ia_na_fila.py -v -s

O que estes testes protegem: o campo é lido pelo WORKER a cada mensagem que
chega num atendimento em fila. Se ele voltar da API sempre `false` — porque
alguém mexeu no `_SELECT_COLS`, no UPDATE ou no índice do `_row_to_departamento`
— o painel mostra o interruptor ligado e o cliente segue sem resposta. A falha
seria silenciosa dos dois lados.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_listar_sem_auth_401(self) -> None:
        assert _client().get("/api/departamentos").status_code == 401

    def test_criar_sem_auth_401(self) -> None:
        resp = _client().post("/api/departamentos", json={"nome": "Suporte"})
        assert resp.status_code == 401

    def test_atualizar_sem_auth_401(self) -> None:
        resp = _client().put("/api/departamentos/1", json={"nome": "Suporte"})
        assert resp.status_code == 401

    def test_rotas_registradas(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/departamentos" in rotas
        assert "/api/departamentos/{dep_id}" in rotas

    def test_campo_no_contrato_de_entrada(self) -> None:
        """Sem isto o PUT aceitaria o campo e descartaria calado."""
        from whatsapp_langchain.shared.models import DepartamentoInput

        entrada = DepartamentoInput(nome="Atendimento", ia_continua_na_fila=True)
        assert entrada.ia_continua_na_fila is True


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================

_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


def _criar_empresa(db_url: str, sufixo: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active')
            RETURNING id
            """,
            (f"test-fila-{sufixo}-{_RUN}", f"test-fila-{sufixo}-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    eid = _criar_empresa(db_url, "a")
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def empresa_vizinha_id(db_url: str):
    """Segundo tenant — prova que o interruptor de um não alcança o outro."""
    eid = _criar_empresa(db_url, "b")
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def user_id(db_url: str, empresa_id: int, empresa_vizinha_id: int):
    uid = f"test-fila-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                     "createdAt", "updatedAt", status,
                                     is_superadmin)
            VALUES (%s, %s, %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (uid, f"Test Fila {_RUN}", f"{uid}@e2e.test"),
        )
        for eid in (empresa_id, empresa_vizinha_id):
            cur.execute(
                """
                INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                VALUES (%s, %s, 'admin', %s)
                """,
                (eid, uid, eid == empresa_id),
            )
    yield uid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    dep_id: int | None = None

    def test_1_nasce_desligado(self, user_id: str, empresa_id: int) -> None:
        """Default FALSE preserva o comportamento de quem já usa fila."""
        r = httpx.post(
            f"{API_BASE_URL}/api/departamentos",
            headers=_headers(user_id, empresa_id),
            json={"nome": f"Atendimento {_RUN}"},
            timeout=30,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["ia_continua_na_fila"] is False
        TestE2E.dep_id = int(body["id"])

    def test_2_ligar_persiste(self, user_id: str, empresa_id: int) -> None:
        assert TestE2E.dep_id is not None
        r = httpx.put(
            f"{API_BASE_URL}/api/departamentos/{TestE2E.dep_id}",
            headers=_headers(user_id, empresa_id),
            json={"nome": f"Atendimento {_RUN}", "ia_continua_na_fila": True},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ia_continua_na_fila"] is True

    def test_3_leitura_direta_confirma(self, user_id: str, empresa_id: int) -> None:
        """É por aqui que o worker lê — GET por id, o mesmo helper."""
        r = httpx.get(
            f"{API_BASE_URL}/api/departamentos/{TestE2E.dep_id}",
            headers=_headers(user_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ia_continua_na_fila"] is True

    def test_4_listagem_traz_o_campo(self, user_id: str, empresa_id: int) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/departamentos",
            headers=_headers(user_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        alvo = [d for d in r.json()["departamentos"] if d["id"] == TestE2E.dep_id]
        assert alvo, "departamento criado não veio na listagem"
        assert alvo[0]["ia_continua_na_fila"] is True

    def test_5_desligar_volta_ao_silencio(self, user_id: str, empresa_id: int) -> None:
        """Contratou alguém pra fila? Desliga e a IA para de novo."""
        r = httpx.put(
            f"{API_BASE_URL}/api/departamentos/{TestE2E.dep_id}",
            headers=_headers(user_id, empresa_id),
            json={"nome": f"Atendimento {_RUN}", "ia_continua_na_fila": False},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ia_continua_na_fila"] is False


@pytest.mark.docker_demo
class TestE2EIsolamento:
    def test_vizinha_nao_enxerga_o_departamento(
        self, user_id: str, empresa_vizinha_id: int
    ) -> None:
        assert TestE2E.dep_id is not None
        r = httpx.get(
            f"{API_BASE_URL}/api/departamentos/{TestE2E.dep_id}",
            headers=_headers(user_id, empresa_vizinha_id),
            timeout=30,
        )
        assert r.status_code == 404, r.text

    def test_vizinha_nao_liga_o_interruptor_alheio(
        self, user_id: str, empresa_vizinha_id: int
    ) -> None:
        """O pior desfecho seria 200 com o UPDATE caindo no vazio."""
        assert TestE2E.dep_id is not None
        r = httpx.put(
            f"{API_BASE_URL}/api/departamentos/{TestE2E.dep_id}",
            headers=_headers(user_id, empresa_vizinha_id),
            json={"nome": "Sequestrado", "ia_continua_na_fila": True},
            timeout=30,
        )
        assert r.status_code == 404, r.text
