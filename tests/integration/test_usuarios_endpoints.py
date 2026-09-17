"""Sprint U.7 — Smoke + E2E dos endpoints /api/usuarios.

Smoke (sem DB): roda em CI, valida 401 sem service token.
E2E (`docker_demo`): fluxo criar→listar→detalhar→atualizar→reset/sessions
em empresa isolada com fixture módulo (CASCADE no teardown).

Para rodar só smoke:
    uv run pytest tests/integration/test_usuarios_endpoints.py::TestSmoke -v

Para rodar E2E (precisa make up):
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_usuarios_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (TestClient — sem DB)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Cada endpoint do router /api/usuarios exige service token."""

    def test_get_list_sem_auth_401(self) -> None:
        assert _client().get("/api/usuarios").status_code == 401

    def test_get_detail_sem_auth_401(self) -> None:
        assert _client().get("/api/usuarios/abc").status_code == 401

    def test_get_exists_sem_auth_401(self) -> None:
        assert _client().get("/api/usuarios/exists/abc").status_code == 401

    def test_post_sem_auth_401(self) -> None:
        r = _client().post("/api/usuarios", json={"nome": "x"})
        assert r.status_code == 401

    def test_put_sem_auth_401(self) -> None:
        r = _client().put("/api/usuarios/x", json={"nome": "y"})
        assert r.status_code == 401

    def test_post_avatar_sem_auth_401(self) -> None:
        assert _client().post("/api/usuarios/x/avatar").status_code == 401

    def test_post_sessions_invalidate_sem_auth_401(self) -> None:
        r = _client().post("/api/usuarios/x/sessions/invalidate")
        assert r.status_code == 401

    def test_patch_status_sem_auth_401(self) -> None:
        r = _client().patch("/api/usuarios/x/status", json={"status": "active"})
        assert r.status_code == 401

    def test_post_replicar_sem_auth_401(self) -> None:
        r = _client().post("/api/usuarios/x/replicar", json={"nome": "z"})
        assert r.status_code == 401

    def test_delete_sem_auth_401(self) -> None:
        assert _client().delete("/api/usuarios/x").status_code == 401

    def test_atividade_sem_auth_401(self) -> None:
        assert _client().get("/api/usuarios/x/atividade").status_code == 401


# ============================================================================
# E2E (stack real)
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


@pytest.fixture(scope="module")
def empresa_id(db_url: str) -> int:
    """Empresa isolada por run; CASCADE drop no teardown."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active')
            RETURNING id
            """,
            (f"test-usu-{_RUN}", f"test-usu-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    """Admin com perfil 'Admin' (todas permissões) + membership."""
    user_id = f"test-usu-admin-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                     "createdAt", "updatedAt", status,
                                     is_superadmin)
            VALUES (%s, 'Admin E2E', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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
        cur.execute(
            """
            INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
            VALUES (%s, 'Admin', 'Acesso total', TRUE)
            ON CONFLICT (empresa_id, nome) DO NOTHING
            RETURNING id
            """,
            (empresa_id,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                (empresa_id,),
            )
            row = cur.fetchone()
        assert row is not None
        perfil_id = int(row[0])
        cur.execute(
            """
            INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
            SELECT %s, codigo FROM permissao
            ON CONFLICT DO NOTHING
            """,
            (perfil_id,),
        )
        cur.execute(
            """
            INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                        assigned_by_user_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (user_id, perfil_id, empresa_id, user_id),
        )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _h(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    """Criar → listar → detalhar → atualizar → exists → invalidar sessions."""

    def test_fluxo_completo(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _h(admin_user_id, empresa_id)

        # 1) GET lista — pelo menos o admin aparece
        r = httpx.get(f"{API_BASE_URL}/api/usuarios", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert any(u["id"] == admin_user_id for u in items)

        # 2) POST criar — só nome (email opcional)
        nome_novo = f"Novo User {_RUN}"
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": nome_novo, "role_legacy": "operator"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        novo = r.json()
        new_id = novo["id"]
        assert novo["nome"] == nome_novo
        # Email sintético gerado pra users sem email
        assert novo["email"] is not None
        assert novo["email"].endswith("@no-email.local")

        try:
            # 3) GET detalhe
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/{new_id}", headers=h, timeout=10
            )
            assert r.status_code == 200, r.text
            assert r.json()["nome"] == nome_novo

            # 4) PUT atualizar nome + telefone
            r = httpx.put(
                f"{API_BASE_URL}/api/usuarios/{new_id}",
                json={"nome": f"{nome_novo} Edit", "telefone": "+5511988887777"},
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json()["nome"] == f"{nome_novo} Edit"
            assert r.json()["telefone"] == "+5511988887777"

            # 5) GET exists — confirma por id (não email)
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/exists/{new_id}",
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text

            # 6) exists pra id inexistente → 404
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/exists/non-existing-id-xyz",
                headers=h,
                timeout=10,
            )
            assert r.status_code == 404

            # 7) POST invalidate sessions — 204 mesmo sem sessions
            r = httpx.post(
                f"{API_BASE_URL}/api/usuarios/{new_id}/sessions/invalidate",
                headers=h,
                timeout=10,
            )
            assert r.status_code == 204, r.text

            # 8) Filtro search — encontra pelo nome
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios?search={_RUN}",
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text
            achados = r.json()["items"]
            assert any(u["id"] == new_id for u in achados), achados

        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM auth."user" WHERE id = %s', (new_id,))

    def test_post_sem_nome_422(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _h(admin_user_id, empresa_id)
        r = httpx.post(f"{API_BASE_URL}/api/usuarios", json={}, headers=h, timeout=10)
        assert r.status_code == 422, r.text

    def test_perfil_de_outra_empresa_422(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        """Validação de tenant: perfil_id inexistente na empresa → 422."""
        h = _h(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": f"Bad {_RUN}", "perfis_ids": [999999]},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 422, r.text

    def test_clonar_usuario(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        """Cria um user com role+perfis e clona — clone herda perfis/role."""
        h = _h(admin_user_id, empresa_id)
        # origem com role admin (sem perfis pra simplificar — perfis exigem id válido)
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": f"Origem {_RUN}", "role_legacy": "admin"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        origem_id = r.json()["id"]
        try:
            r = httpx.post(
                f"{API_BASE_URL}/api/usuarios/{origem_id}/replicar",
                json={"nome": f"Clone {_RUN}"},
                headers=h,
                timeout=10,
            )
            assert r.status_code == 201, r.text
            clone = r.json()
            clone_id = clone["id"]
            assert clone["nome"] == f"Clone {_RUN}"
            assert clone["role_legacy"] == "admin"
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (clone_id,))
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (origem_id,))

    def test_status_disable_reactivate_e_delete(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _h(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": f"Temp {_RUN}"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        uid = r.json()["id"]

        # desativar (sem atendimentos → transferidos=0)
        r = httpx.patch(
            f"{API_BASE_URL}/api/usuarios/{uid}/status",
            json={"status": "disabled", "on_disable": "none"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["transferidos"] == 0

        # reativar
        r = httpx.patch(
            f"{API_BASE_URL}/api/usuarios/{uid}/status",
            json={"status": "active"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text

        # atividade: registra disable + enable, com nome do ator resolvido
        r = httpx.get(
            f"{API_BASE_URL}/api/usuarios/{uid}/atividade", headers=h, timeout=10
        )
        assert r.status_code == 200, r.text
        eventos = r.json()["items"]
        acoes = {e["action"] for e in eventos}
        assert "member.disable" in acoes, eventos
        assert "member.enable" in acoes, eventos
        assert any(e.get("actor_nome") for e in eventos), eventos

        # reassign sem target → 422 (model validator)
        r = httpx.patch(
            f"{API_BASE_URL}/api/usuarios/{uid}/status",
            json={"status": "disabled", "on_disable": "reassign"},
            headers=h,
            timeout=10,
        )
        assert r.status_code == 422, r.text

        # DELETE → 204; depois GET → 404
        r = httpx.delete(f"{API_BASE_URL}/api/usuarios/{uid}", headers=h, timeout=10)
        assert r.status_code == 204, r.text
        r = httpx.get(f"{API_BASE_URL}/api/usuarios/{uid}", headers=h, timeout=10)
        assert r.status_code == 404, r.text

    def test_delete_self_400(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _h(admin_user_id, empresa_id)
        r = httpx.delete(
            f"{API_BASE_URL}/api/usuarios/{admin_user_id}", headers=h, timeout=10
        )
        assert r.status_code == 400, r.text


@pytest.fixture(scope="module")
def empresa_b_id(db_url: str) -> int:
    """2ª empresa pra testes de isolamento cross-tenant."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active') RETURNING id
            """,
            (f"test-usu-b-{_RUN}", f"test-usu-b-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_b_id(db_url: str, empresa_b_id: int) -> str:
    """Superadmin da empresa B (vê só a B via X-Empresa-Id)."""
    user_id = f"test-usu-admin-b-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                     "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Admin B', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            """
            INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
            VALUES (%s, %s, 'admin', TRUE)
            """,
            (empresa_b_id, user_id),
        )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Empresa B não enxerga nem mexe em usuário da empresa A."""

    def test_cross_empresa_get_e_delete_404(
        self,
        db_url: str,
        empresa_id: int,
        admin_user_id: str,
        empresa_b_id: int,
        admin_b_id: str,
    ) -> None:
        # Cria user na empresa A
        ha = _h(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": f"AonlyA {_RUN}"},
            headers=ha,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        uid_a = r.json()["id"]
        try:
            hb = _h(admin_b_id, empresa_b_id)
            # B não vê A na listagem
            r = httpx.get(f"{API_BASE_URL}/api/usuarios", headers=hb, timeout=10)
            assert r.status_code == 200, r.text
            assert all(u["id"] != uid_a for u in r.json()["items"])
            # B não detalha A → 404
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/{uid_a}", headers=hb, timeout=10
            )
            assert r.status_code == 404, r.text
            # B não deleta A → 404
            r = httpx.delete(
                f"{API_BASE_URL}/api/usuarios/{uid_a}", headers=hb, timeout=10
            )
            assert r.status_code == 404, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid_a,))

    def test_cross_empresa_exists_e_sessions_invalidate_404(
        self,
        db_url: str,
        empresa_id: int,
        admin_user_id: str,
        empresa_b_id: int,
        admin_b_id: str,
    ) -> None:
        """Red team A2/M11: antes da correção, B confirmava existência
        (nome/email) e forçava logout de A sem ser membro da empresa dele —
        IDOR cross-tenant. `exists` e `sessions/invalidate` fazem lookup
        GLOBAL em `auth.user`/`auth.session` (sem RLS); o guard de empresa
        tem que vir do handler, não do banco."""
        ha = _h(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            json={"nome": f"AonlyA-idor {_RUN}"},
            headers=ha,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        uid_a = r.json()["id"]
        try:
            hb = _h(admin_b_id, empresa_b_id)
            # B não confirma existência de A → 404 (não revela nome/email)
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/exists/{uid_a}", headers=hb, timeout=10
            )
            assert r.status_code == 404, r.text
            # B não força logout de A → 404, sessão de A intacta
            r = httpx.post(
                f"{API_BASE_URL}/api/usuarios/{uid_a}/sessions/invalidate",
                headers=hb,
                timeout=10,
            )
            assert r.status_code == 404, r.text
            # O dono de A (empresa correta) segue confirmando existência normal
            r = httpx.get(
                f"{API_BASE_URL}/api/usuarios/exists/{uid_a}", headers=ha, timeout=10
            )
            assert r.status_code == 200, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid_a,))
