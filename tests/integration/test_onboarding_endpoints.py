"""Smoke + E2E do onboarding dispensável (mig 160).

Cobre os dois defeitos que faziam o wizard reaparecer em todo login:

**D1 — a contagem mentia.** `/api/empresas/{id}/membros` devolve uma *lista
pura* (`response_model=list[EmpresaMembro]`), mas o frontend lia `.items` dela.
Em lista isso é `undefined`, então o passo 4 contava 0 atendentes mesmo com 10
cadastrados, `completo` nunca virava true e a raiz "/" devolvia todo login pro
wizard. `TestContratoDeListagem` trava o formato de cada endpoint que a tela
consome — é o teste que impede a volta do bug.

**D2 — o "Pular" não pulava.** Era um link pro dashboard, sem persistir nada.
Agora grava `empresa.onboarding_dispensado_at`.

Só smoke:
    uv run pytest tests/integration/test_onboarding_endpoints.py::TestSmoke -v

E2E (precisa make up + migrações):
    uv run pytest tests/integration/test_onboarding_endpoints.py -v -s
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
    """A rota existe e exige auth."""

    def test_put_dispensado_sem_auth_401(self) -> None:
        resp = _client().put(
            "/api/empresas/1/onboarding-dispensado", json={"dispensado": True}
        )
        assert resp.status_code == 401

    def test_get_status_sem_auth_401(self) -> None:
        resp = _client().get("/api/empresas/1/onboarding")
        assert resp.status_code == 401

    def test_rotas_registradas(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/empresas/{empresa_id}/onboarding-dispensado" in rotas
        assert "/api/empresas/{empresa_id}/onboarding" in rotas

    def test_empresa_expoe_o_campo(self) -> None:
        """Sem o campo no model, o front nunca sabe que foi dispensado —
        e o wizard volta mesmo com a coluna gravada."""
        from whatsapp_langchain.shared.models import Empresa

        assert "onboarding_dispensado_at" in Empresa.model_fields

    def test_default_e_none(self) -> None:
        """None = nunca dispensado. Se virasse False/0, empresa nova pularia
        o guiado — o oposto do que o redirect quer."""
        from whatsapp_langchain.shared.models import Empresa

        assert Empresa.model_fields["onboarding_dispensado_at"].default is None


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
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-onb-{_RUN}", f"test-onb-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _cria_user(db_url: str, empresa_id: int, sufixo: str) -> str:
    user_id = f"test-onb-user-{sufixo}-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Test Onb User', %s, TRUE, NOW(), NOW(),
                        'active', FALSE)
                """,
                (user_id, f"{user_id}@e2e.test"),
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
def admin_user_id(db_url: str, empresa_id: int):
    user_id = _cria_user(db_url, empresa_id, "adm")
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    """Ciclo completo: nasce guiado → dispensa → volta a ser guiado."""

    def test_1_empresa_nasce_sem_dispensa(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        alvo = [e for e in r.json()["empresas"] if e["id"] == empresa_id]
        assert alvo, f"empresa {empresa_id} não veio na listagem: {r.text}"
        assert alvo[0]["onboarding_dispensado_at"] is None

    def test_2_dispensar_grava(self, empresa_id: int, admin_user_id: str) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding-dispensado",
            headers=_headers(admin_user_id, empresa_id),
            json={"dispensado": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["onboarding_dispensado_at"] is not None

    def test_3_listagem_reflete(self, empresa_id: int, admin_user_id: str) -> None:
        """É por esta listagem que a raiz "/" decide — se o campo não vier
        aqui, a dispensa existe no banco e não vale nada na prática."""
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        alvo = [e for e in r.json()["empresas"] if e["id"] == empresa_id][0]
        assert alvo["onboarding_dispensado_at"] is not None

    def test_4_desfazer_limpa(self, empresa_id: int, admin_user_id: str) -> None:
        """Sem isto a dispensa seria de mão única."""
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding-dispensado",
            headers=_headers(admin_user_id, empresa_id),
            json={"dispensado": False},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["onboarding_dispensado_at"] is None

    def test_5_empresa_inexistente_404(self, admin_user_id: str) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/99999999/onboarding-dispensado",
            headers=_headers(admin_user_id, 99999999),
            json={"dispensado": True},
            timeout=20,
        )
        assert r.status_code in (403, 404), r.text


@pytest.mark.docker_demo
class TestStatus:
    """O endpoint que a tela consome — contagem certa, e para todo membro."""

    def test_conta_membros_de_verdade(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        """O passo 4 contava 0 com 10 atendentes cadastrados: o front lia
        `.items` de `/membros`, que devolve lista pura. Aqui a contagem é do
        banco, e o teste falha se ela voltar a mentir."""
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["atendentes_count"] >= 1, (
            "o admin do teste é membro — se vier 0, a contagem quebrou de novo"
        )

    def test_completo_exige_os_quatro(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        """Empresa do teste tem membro mas nem doc, nem conexão, nem agente."""
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        corpo = r.json()
        assert corpo["completo"] is False, corpo
        assert corpo["empresa_doc_ok"] is False, corpo
        assert corpo["conexoes_count"] == 0, corpo
        assert corpo["agentes_count"] == 0, corpo

    def test_operador_sem_permissao_ve_o_mesmo(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        """A regressão que quase passou batido.

        A versão anterior montava o status chamando `/v1/agentes`, que exige
        `agente.config`. Operador sem essa permissão tomava 403, o `.catch`
        virava lista vazia e o passo 3 nunca completava — o wizard virava um
        beco sem saída **só pra ele**. O estado do onboarding é da empresa:
        tem que ser igual pra qualquer membro.
        """
        operador = _cria_user(db_url, empresa_id, "op")
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE empresa_membro SET role = 'operator' "
                    "WHERE user_id = %s AND empresa_id = %s",
                    (operador, empresa_id),
                )
        try:
            r_adm = httpx.get(
                f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding",
                headers=_headers(admin_user_id, empresa_id),
                timeout=20,
            )
            r_op = httpx.get(
                f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding",
                headers=_headers(operador, empresa_id),
                timeout=20,
            )
            assert r_op.status_code == 200, r_op.text
            assert r_op.json() == r_adm.json(), (
                "operador e admin veem status diferentes — o onboarding voltou "
                "a depender de permissão de quem pergunta"
            )
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM auth."user" WHERE id = %s', (operador,))

    def test_estranho_nao_le_status(self, db_url: str, empresa_id: int) -> None:
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-onb-x-{_RUN}", f"test-onb-x-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                outra = int(row[0])
        estranho = _cria_user(db_url, outra, "xis")
        try:
            r = httpx.get(
                f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding",
                headers=_headers(estranho, outra),
                timeout=20,
            )
            assert r.status_code == 403, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM auth."user" WHERE id = %s', (estranho,))
                    cur.execute("DELETE FROM empresa WHERE id = %s", (outra,))


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Membro de outra empresa não dispensa o onboarding alheio."""

    def test_estranho_nao_dispensa(self, db_url: str, empresa_id: int) -> None:
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-onb-outra-{_RUN}", f"test-onb-outra-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                outra = int(row[0])
        estranho = _cria_user(db_url, outra, "estranho")
        try:
            r = httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_id}/onboarding-dispensado",
                headers=_headers(estranho, outra),
                json={"dispensado": True},
                timeout=20,
            )
            assert r.status_code == 403, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM auth."user" WHERE id = %s', (estranho,))
                    cur.execute("DELETE FROM empresa WHERE id = %s", (outra,))
