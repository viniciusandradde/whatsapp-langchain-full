"""Smoke + E2E dos endpoints de tag (Sprint Atendimento UX 1.2).

Modelo canônico: tests/integration/test_aba_endpoints.py.

Para smoke (sem DB):
    uv run pytest tests/integration/test_tag_endpoints.py::TestSmoke -v

Para E2E (precisa make up):
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_tag_endpoints.py -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


# ============================================================================
# Smoke (TestClient, sem DB)
# ============================================================================


class TestSmoke:
    """Rotas existem + exigem service token."""

    def test_get_tags_sem_auth_401(self) -> None:
        assert _client().get("/api/tags").status_code == 401

    def test_post_tag_sem_auth_401(self) -> None:
        assert (
            _client().post("/api/tags", json={"nome": "X"}).status_code == 401
        )

    def test_patch_tag_sem_auth_401(self) -> None:
        assert (
            _client().patch("/api/tags/1", json={"nome": "Y"}).status_code == 401
        )

    def test_delete_tag_sem_auth_401(self) -> None:
        assert _client().delete("/api/tags/1").status_code == 401

    def test_get_tags_atendimento_sem_auth_401(self) -> None:
        assert _client().get("/api/atendimentos/1/tags").status_code == 401

    def test_post_apply_tags_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/atendimentos/1/tags", json={"add": [1], "remove": []}
        )
        assert resp.status_code == 401


# ============================================================================
# E2E (stack real)
# ============================================================================


_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    """Skip se stack não tá rodando."""
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
def empresa_id(db_url: str) -> int:
    """Cria empresa isolada. CASCADE limpa tag/atendimento/perfil_acesso no fim."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-tag-{_RUN}", f"test-tag-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    """User com perfil Admin (tem tag.manage + atendimento.tag.aplicar)."""
    user_id = f"test-tag-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Tag E2E User', %s, TRUE,
                        NOW(), NOW(), 'active', FALSE)
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
                SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING
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
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.fixture(scope="module")
def atendimento_id(db_url: str, empresa_id: int) -> int:
    """Cria conexão + cliente + atendimento isolados."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                      display_name, status)
                VALUES (%s, 'twilio_sandbox', %s, %s, 'active')
                RETURNING id
                """,
                (empresa_id, f"+155501{_RUN[:5]}", f"conn-tag-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            cid = int(row[0])

            cur.execute(
                """
                INSERT INTO cliente (empresa_id, telefone, nome, status)
                VALUES (%s, %s, 'Cliente Tag E2E', 'active')
                RETURNING id
                """,
                (empresa_id, f"+5511990{_RUN[:5]}"),
            )
            row = cur.fetchone()
            assert row is not None
            cli_id = int(row[0])

            cur.execute(
                """
                INSERT INTO atendimento (empresa_id, cliente_id, conexao_id,
                                          status, last_message_at)
                VALUES (%s, %s, %s, 'aguardando', NOW())
                RETURNING id
                """,
                (empresa_id, cli_id, cid),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo completo: criar tag → aplicar → filtrar → remover → delete."""

    def test_fluxo_completo_tag(
        self, db_url: str, empresa_id: int, admin_user_id: str, atendimento_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)

        # --- 1. GET /tags — começa vazio (empresa isolada)
        r = httpx.get(f"{API_BASE_URL}/api/tags", headers=h, timeout=5)
        assert r.status_code == 200, r.text
        assert r.json() == {"items": []}

        # --- 2. POST /tags — cria 2 tags
        r1 = httpx.post(
            f"{API_BASE_URL}/api/tags",
            json={"nome": f"VIP {_RUN}", "cor": "#dc2626"},
            headers=h,
            timeout=5,
        )
        assert r1.status_code == 200, r1.text
        tag1 = r1.json()
        assert tag1["nome"] == f"VIP {_RUN}"
        assert tag1["cor"] == "#dc2626"
        assert tag1["ativo"] is True

        r2 = httpx.post(
            f"{API_BASE_URL}/api/tags",
            json={"nome": f"Urgente {_RUN}", "cor": "#2563eb"},
            headers=h,
            timeout=5,
        )
        assert r2.status_code == 200, r2.text
        tag2 = r2.json()

        # --- 3. POST /tags duplicado → 409
        r_dup = httpx.post(
            f"{API_BASE_URL}/api/tags",
            json={"nome": f"VIP {_RUN}"},
            headers=h,
            timeout=5,
        )
        assert r_dup.status_code == 409, r_dup.text

        # --- 4. GET /tags — lista as 2 ordenadas por nome
        r = httpx.get(f"{API_BASE_URL}/api/tags", headers=h, timeout=5)
        items = r.json()["items"]
        assert len(items) == 2
        # Ordem alfabética: "Urgente" < "VIP" → ATENÇÃO: 'U' (85) < 'V' (86)
        assert items[0]["nome"] == f"Urgente {_RUN}"
        assert items[1]["nome"] == f"VIP {_RUN}"

        # --- 5. PATCH /tags/{id} — renomeia e troca cor
        r = httpx.patch(
            f"{API_BASE_URL}/api/tags/{tag2['id']}",
            json={"nome": f"Crítico {_RUN}", "cor": "#ea580c"},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == f"Crítico {_RUN}"
        assert r.json()["cor"] == "#ea580c"

        # --- 6. POST /atendimentos/{id}/tags — aplica 2 tags
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/tags",
            json={"add": [tag1["id"], tag2["id"]], "remove": []},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 2
        assert r.json()["removed"] == 0

        # --- 7. GET /atendimentos/{id}/tags — vê as 2
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/tags",
            headers=h,
            timeout=5,
        )
        items = r.json()["items"]
        assert len(items) == 2
        # Aplicado por humano: user_id setado, por_ia=False
        for item in items:
            assert item["aplicado_por_user_id"] == admin_user_id
            assert item["aplicado_por_ia"] is False

        # --- 8. Re-aplicar é idempotente (ON CONFLICT DO NOTHING)
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/tags",
            json={"add": [tag1["id"]], "remove": []},
            headers=h,
            timeout=5,
        )
        assert r.json()["added"] == 0  # já existia

        # --- 9. GET /atendimentos?tag_id=N — filtra por tag (OR)
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos?tag_id={tag1['id']}&tipo=outros",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        atds = r.json()["atendimentos"]
        assert any(a["id"] == atendimento_id for a in atds)

        # --- 10. GET /atendimentos?tag_id=NONEXISTENT — vazio
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos?tag_id=999999&tipo=outros",
            headers=h,
            timeout=5,
        )
        assert r.json()["atendimentos"] == []

        # --- 11. POST /atendimentos/{id}/tags com remove
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/tags",
            json={"add": [], "remove": [tag2["id"]]},
            headers=h,
            timeout=5,
        )
        assert r.json()["removed"] == 1

        # Confirma direto no DB
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tag_id FROM atendimento_tag WHERE atendimento_id = %s",
                    (atendimento_id,),
                )
                tag_ids_db = [r[0] for r in cur.fetchall()]
        assert tag_ids_db == [tag1["id"]]

        # --- 12. DELETE /tags/{id} CASCADE em atendimento_tag
        r = httpx.delete(
            f"{API_BASE_URL}/api/tags/{tag1['id']}", headers=h, timeout=5
        )
        assert r.status_code == 200, r.text
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM atendimento_tag WHERE atendimento_id = %s",
                    (atendimento_id,),
                )
                row = cur.fetchone()
                assert row is not None and row[0] == 0, (
                    "DELETE tag deve cascatear em atendimento_tag"
                )

        # --- 13. DELETE tag inexistente → 404
        r = httpx.delete(
            f"{API_BASE_URL}/api/tags/999999", headers=h, timeout=5
        )
        assert r.status_code == 404

        # --- 14. PATCH tag inexistente → 404
        r = httpx.patch(
            f"{API_BASE_URL}/api/tags/999999",
            json={"nome": "X"},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Cross-empresa: tag de empresa A NÃO é visível pra empresa B."""

    def test_tag_de_outra_empresa_nao_aparece(self, db_url: str) -> None:
        # Empresa A + user A
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active')
                    RETURNING id
                    """,
                    (f"test-tag-iso-A-{_RUN}", f"test-tag-iso-A-{_RUN}"),
                )
                row_a = cur.fetchone()
                assert row_a is not None
                emp_a = int(row_a[0])
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active')
                    RETURNING id
                    """,
                    (f"test-tag-iso-B-{_RUN}", f"test-tag-iso-B-{_RUN}"),
                )
                row_b = cur.fetchone()
                assert row_b is not None
                emp_b = int(row_b[0])

                user_a = f"test-tag-iso-a-{_RUN}"
                user_b = f"test-tag-iso-b-{_RUN}"
                for uid, eid in ((user_a, emp_a), (user_b, emp_b)):
                    cur.execute(
                        """
                        INSERT INTO auth."user" (id, name, email, "emailVerified",
                                                  "createdAt", "updatedAt", status,
                                                  is_superadmin)
                        VALUES (%s, 'Iso User', %s, TRUE,
                                NOW(), NOW(), 'active', FALSE)
                        """,
                        (uid, f"{uid}@iso.test"),
                    )
                    cur.execute(
                        """
                        INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                        VALUES (%s, %s, 'admin', TRUE)
                        """,
                        (eid, uid),
                    )
                    cur.execute(
                        """
                        INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                        VALUES (%s, 'Admin', 'Acesso total', TRUE)
                        ON CONFLICT (empresa_id, nome) DO NOTHING
                        RETURNING id
                        """,
                        (eid,),
                    )
                    prow = cur.fetchone()
                    if prow is None:
                        cur.execute(
                            "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                            (eid,),
                        )
                        prow = cur.fetchone()
                    assert prow is not None
                    pf_id = int(prow[0])
                    cur.execute(
                        """
                        INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                        SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING
                        """,
                        (pf_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                                    assigned_by_user_id)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (uid, pf_id, eid, uid),
                    )

        try:
            # A cria tag
            ra = httpx.post(
                f"{API_BASE_URL}/api/tags",
                json={"nome": f"Privada A {_RUN}", "cor": "#000"},
                headers=_headers(user_a, emp_a),
                timeout=5,
            )
            assert ra.status_code == 200, ra.text
            tag_a = ra.json()

            # B NÃO vê
            rb = httpx.get(
                f"{API_BASE_URL}/api/tags",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert rb.status_code == 200, rb.text
            assert all(t["id"] != tag_a["id"] for t in rb.json()["items"]), (
                "Empresa B vê tag de empresa A!"
            )

            # B tenta editar tag de A → 404
            rb = httpx.patch(
                f"{API_BASE_URL}/api/tags/{tag_a['id']}",
                json={"nome": "Hijack"},
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert rb.status_code == 404

            # B tenta deletar → 404
            rb = httpx.delete(
                f"{API_BASE_URL}/api/tags/{tag_a['id']}",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert rb.status_code == 404
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM empresa WHERE id IN (%s, %s)", (emp_a, emp_b))
