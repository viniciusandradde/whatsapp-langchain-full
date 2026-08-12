"""Smoke + E2E do Módulo de Uso (mig 165).

Smoke (sem DB): rotas existem e exigem service token. Roda em CI.
E2E (stack real): listar → prévia → PDF → config → enviar.

    uv run pytest tests/integration/test_relatorio_uso_endpoints.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_relatorio_uso_endpoints.py -v -s

O guarda deste módulo é **superadmin**, não RBAC de tenant — por isso a classe
de isolamento verifica 403 para um usuário admin comum, e não a ausência de uma
permissão específica.
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
    def test_listar_empresas_sem_auth_401(self) -> None:
        assert _client().get("/api/relatorios/uso/empresas").status_code == 401

    def test_ler_relatorio_sem_auth_401(self) -> None:
        assert _client().get("/api/relatorios/uso/1").status_code == 401

    def test_pdf_sem_auth_401(self) -> None:
        assert _client().get("/api/relatorios/uso/1/pdf").status_code == 401

    def test_enviar_sem_auth_401(self) -> None:
        resp = _client().post("/api/relatorios/uso/1/enviar", json={})
        assert resp.status_code == 401

    def test_ler_config_sem_auth_401(self) -> None:
        assert _client().get("/api/relatorios/uso/1/config").status_code == 401

    def test_salvar_config_sem_auth_401(self) -> None:
        resp = _client().put("/api/relatorios/uso/1/config", json={"ativo": False})
        assert resp.status_code == 401

    def test_rotas_registradas(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/relatorios/uso/empresas" in rotas
        assert "/api/relatorios/uso/{empresa_id}/pdf" in rotas


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================

pytestmark_e2e = pytest.mark.docker_demo

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


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active')
            RETURNING id
            """,
            (f"test-uso-{_RUN}", f"test-uso-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _criar_user(db_url: str, empresa_id: int, sufixo: str, *, superadmin: bool) -> str:
    user_id = f"test-uso-{sufixo}-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, %s, %s, TRUE, NOW(), NOW(), 'active', %s)
            """,
            (user_id, f"Test Uso {sufixo}", f"{user_id}@e2e.test", superadmin),
        )
        cur.execute(
            """
            INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
            VALUES (%s, %s, 'admin', TRUE)
            """,
            (empresa_id, user_id),
        )
    return user_id


@pytest.fixture(scope="module")
def superadmin_id(db_url: str, empresa_id: int):
    uid = _criar_user(db_url, empresa_id, "super", superadmin=True)
    yield uid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))


@pytest.fixture(scope="module")
def admin_comum_id(db_url: str, empresa_id: int):
    """Admin da empresa, SEM superadmin — quem não pode abrir o módulo."""
    uid = _criar_user(db_url, empresa_id, "comum", superadmin=False)
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
    def test_1_lista_traz_a_empresa_com_o_motivo(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        """Empresa recém-criada não tem conexão nem telefone — precisa aparecer
        assim mesmo, com o motivo, em vez de sumir da lista."""
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/empresas",
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        clientes = r.json()["clientes"]
        alvo = [c for c in clientes if c["empresa_id"] == empresa_id]
        assert alvo, f"empresa {empresa_id} não veio na lista"
        assert alvo[0]["pode_enviar"] is False
        assert "conexão" in (alvo[0]["motivo"] or "")

    def test_2_relatorio_de_mes_vazio_devolve_zeros(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}",
            params={"competencia": "2026-01"},
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["competencia"] == "2026-01"
        assert d["totais"]["mensagens"] == 0
        assert d["diario"] == []

    def test_3_competencia_invalida_e_400(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}",
            params={"competencia": "2026-13"},
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 400, r.text
        assert "AAAA-MM" in r.json()["detail"]

    def test_4_pdf_sai_mesmo_sem_movimento(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        """Cliente novo também recebe relatório — "nenhuma mensagem" é uma
        informação, e um 500 aqui quebraria o envio mensal do primeiro mês."""
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/pdf",
            params={"competencia": "2026-01"},
            headers=_headers(superadmin_id, empresa_id),
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
        assert "Relatorio-de-Uso" in r.headers.get("content-disposition", "")

    def test_5_config_nasce_desligada(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/config",
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ativo"] is False
        assert r.json()["dia"] == 1

    def test_6_ativar_sem_telefone_e_recusado(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/config",
            json={"ativo": True, "telefone": None},
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 400, r.text
        assert "telefone" in r.json()["detail"].lower()

    def test_7_salvar_config_completa(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/config",
            json={
                "ativo": True,
                "telefone": "+5567999068963",
                "dia": 3,
                "horario": "08:30",
                "tz": "America/Campo_Grande",
            },
            headers=_headers(superadmin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ativo"] is True
        assert d["telefone"] == "+5567999068963"
        assert d["dia"] == 3
        assert d["horario"] == "08:30"

    def test_8_enviar_sem_conexao_devolve_200_com_motivo(
        self, superadmin_id: str, empresa_id: int
    ) -> None:
        """A falha é do WhatsApp, não da nossa API: 200 com `ok: false` e o
        motivo em texto, para a tela mostrar. 5xx viraria "erro interno"."""
        r = httpx.post(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/enviar",
            json={"competencia": "2026-01"},
            headers=_headers(superadmin_id, empresa_id),
            timeout=60,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["ok"] is False
        assert "conexão" in corpo["erro"]


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Admin de empresa NÃO abre o módulo — ele é de plataforma."""

    def test_listar_nega_para_admin_comum(
        self, admin_comum_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/empresas",
            headers=_headers(admin_comum_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_relatorio_nega_para_admin_comum(
        self, admin_comum_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}",
            headers=_headers(admin_comum_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_pdf_nega_para_admin_comum(
        self, admin_comum_id: str, empresa_id: int
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/pdf",
            headers=_headers(admin_comum_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_enviar_nega_para_admin_comum(
        self, admin_comum_id: str, empresa_id: int
    ) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/enviar",
            json={},
            headers=_headers(admin_comum_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_config_nega_para_admin_comum(
        self, admin_comum_id: str, empresa_id: int
    ) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/relatorios/uso/{empresa_id}/config",
            json={"ativo": False},
            headers=_headers(admin_comum_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 403, r.text
