"""Smoke + E2E dos endpoints de aba (Sprint Atendimento UX, mig 085).

Smoke (sem DB): valida que rotas existem e exigem service token.
E2E (com stack rodando): fluxo completo criar→atribuir→contadores→delete.

Para rodar só smoke:
    uv run pytest tests/integration/test_aba_endpoints.py::TestSmoke -v

Para rodar E2E (precisa make up + migrações aplicadas):
    uv run pytest tests/integration/test_aba_endpoints.py::TestE2E -v -s
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
    """Verifica que as rotas estão registradas e exigem auth."""

    def test_get_my_abas_sem_auth_401(self) -> None:
        resp = _client().get("/api/abas/me")
        assert resp.status_code == 401

    def test_post_aba_sem_auth_401(self) -> None:
        resp = _client().post("/api/abas", json={"descricao": "X"})
        assert resp.status_code == 401

    def test_patch_aba_sem_auth_401(self) -> None:
        resp = _client().patch("/api/abas/1", json={"descricao": "Y"})
        assert resp.status_code == 401

    def test_delete_aba_sem_auth_401(self) -> None:
        resp = _client().delete("/api/abas/1")
        assert resp.status_code == 401

    def test_reorder_aba_sem_auth_401(self) -> None:
        resp = _client().post("/api/abas/reorder", json={"ordered_ids": []})
        assert resp.status_code == 401

    def test_contadores_sem_auth_401(self) -> None:
        resp = _client().get("/api/atendimentos/contadores")
        assert resp.status_code == 401

    def test_attach_aba_sem_auth_401(self) -> None:
        resp = _client().post("/api/atendimentos/1/aba", json={"aba_id": 1})
        assert resp.status_code == 401


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================


pytestmark_e2e = pytest.mark.docker_demo

# Sufixo curto pra isolar dados deste run de testes paralelos/repetidos
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
    """Cria empresa isolada pro teste. Cleanup no fim do módulo (CASCADE)."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-aba-{_RUN}", f"test-aba-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    # CASCADE limpa empresa_membro, aba (via empresa_id FK), atendimento (via FK)
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    """Cria user no auth.user + empresa_membro admin + perfil 'Admin'.

    Admin tem todas perms (incluindo `atendimento.aba.manage`).
    """
    user_id = f"test-aba-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            # auth.user — required por FK em empresa_membro
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Test Aba User',
                        %s, TRUE, NOW(), NOW(), 'active', FALSE)
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
            # Garantir que o perfil Admin existe pra essa empresa e atribuir
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
            # Adiciona TODAS as permissões ao perfil Admin desta empresa
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
    # auth.user CASCADE limpa empresa_membro + usuario_perfil
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    """Auth completo: service token + headers do frontend."""
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.fixture(scope="module")
def atendimento_id(db_url: str, empresa_id: int) -> int:
    """Cria cliente + conexão + atendimento mínimos pra teste."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Conexão
            cur.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                      display_name, status)
                VALUES (%s, 'twilio_sandbox', %s, %s, 'active')
                RETURNING id
                """,
                (empresa_id, f"+155500{_RUN[:5]}", f"conn-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            cid = int(row[0])

            # Cliente
            phone = f"+551199{_RUN[:6]}"
            cur.execute(
                """
                INSERT INTO cliente (empresa_id, telefone, nome, status)
                VALUES (%s, %s, 'Cliente E2E', 'active')
                RETURNING id
                """,
                (empresa_id, phone),
            )
            row = cur.fetchone()
            assert row is not None
            cli_id = int(row[0])

            # Atendimento aberto
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
            aid = int(row[0])
    return aid


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo completo: criar aba → atribuir atendimento → contadores → delete."""

    def test_fluxo_completo_aba(
        self, db_url: str, empresa_id: int, admin_user_id: str, atendimento_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)

        # --- 1. GET /abas/me — começa vazio ---
        r = httpx.get(f"{API_BASE_URL}/api/abas/me", headers=h, timeout=5)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"items": []}

        # --- 2. POST /abas — cria 2 abas ---
        r1 = httpx.post(
            f"{API_BASE_URL}/api/abas",
            json={"descricao": f"VIPs {_RUN}", "cor": "#dc2626"},
            headers=h,
            timeout=5,
        )
        assert r1.status_code == 200, r1.text
        aba1 = r1.json()
        assert aba1["descricao"] == f"VIPs {_RUN}"
        assert aba1["cor"] == "#dc2626"
        assert aba1["ordem"] == 0

        r2 = httpx.post(
            f"{API_BASE_URL}/api/abas",
            json={"descricao": f"Pendentes {_RUN}", "cor": "#2563eb"},
            headers=h,
            timeout=5,
        )
        assert r2.status_code == 200, r2.text
        aba2 = r2.json()
        assert aba2["ordem"] == 1, "segunda aba deve ter ordem auto = 1"

        # --- 3. GET /abas/me — lista as 2, ordenadas ---
        r = httpx.get(f"{API_BASE_URL}/api/abas/me", headers=h, timeout=5)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["id"] == aba1["id"]
        assert items[1]["id"] == aba2["id"]

        # --- 4. POST /abas — UNIQUE viola → 409 ---
        r_dup = httpx.post(
            f"{API_BASE_URL}/api/abas",
            json={"descricao": f"VIPs {_RUN}"},
            headers=h,
            timeout=5,
        )
        assert r_dup.status_code == 409, f"esperado 409, foi {r_dup.status_code}"

        # --- 5. PATCH /abas/{id} — rename + cor nova ---
        r = httpx.patch(
            f"{API_BASE_URL}/api/abas/{aba2['id']}",
            json={"descricao": f"Urgentes {_RUN}", "cor": "#ea580c"},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        upd = r.json()
        assert upd["descricao"] == f"Urgentes {_RUN}"
        assert upd["cor"] == "#ea580c"

        # --- 6. POST /atendimentos/{id}/aba — pinning ---
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/aba",
            json={"aba_id": aba1["id"]},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["aba_id"] == aba1["id"]

        # Verifica direto no DB
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT aba_id FROM atendimento WHERE id = %s",
                    (atendimento_id,),
                )
                row = cur.fetchone()
                assert row is not None and row[0] == aba1["id"]

        # --- 7. GET /atendimentos/contadores — vê o pin na aba1 ---
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/contadores",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        cont = r.json()
        assert cont["abas"][str(aba1["id"])] == 1
        assert str(aba2["id"]) not in cont["abas"]  # aba2 vazia
        # Sistema: 1 aguardando (o atendimento criado)
        assert cont["sistema"]["aguardando"] >= 1

        # --- 8. Listar atendimentos filtrado por aba_id ---
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos?aba_id={aba1['id']}",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        atds = r.json()["atendimentos"]
        assert len(atds) == 1
        assert atds[0]["id"] == atendimento_id
        assert atds[0]["aba_id"] == aba1["id"]

        # --- 9. POST /atendimentos/{id}/aba com aba_id=null — desatribui ---
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/aba",
            json={"aba_id": None},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT aba_id FROM atendimento WHERE id = %s",
                    (atendimento_id,),
                )
                row = cur.fetchone()
                assert row is not None and row[0] is None

        # --- 10. POST /aba inválida (id alheio) → 404 ---
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/aba",
            json={"aba_id": 999_999},  # aba que não existe
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404

        # --- 11. Re-pinning + DELETE aba → atendimento desatribuído automaticamente ---
        httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/aba",
            json={"aba_id": aba1["id"]},
            headers=h,
            timeout=5,
        )
        r = httpx.delete(
            f"{API_BASE_URL}/api/abas/{aba1['id']}", headers=h, timeout=5
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # Atendimento agora tá sem aba (delete fez UPDATE aba_id=NULL)
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT aba_id FROM atendimento WHERE id = %s",
                    (atendimento_id,),
                )
                row = cur.fetchone()
                assert row is not None and row[0] is None, (
                    "DELETE aba deveria limpar pin"
                )

        # --- 12. GET abas — aba1 sumiu (soft delete, ativo=FALSE) ---
        r = httpx.get(f"{API_BASE_URL}/api/abas/me", headers=h, timeout=5)
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == aba2["id"]

        # --- 13. DELETE de aba inexistente → 404 ---
        r = httpx.delete(
            f"{API_BASE_URL}/api/abas/999999", headers=h, timeout=5
        )
        assert r.status_code == 404

        # --- 14. Reorder muda ordem ---
        r3 = httpx.post(
            f"{API_BASE_URL}/api/abas",
            json={"descricao": f"NovaC {_RUN}"},
            headers=h,
            timeout=5,
        )
        aba3 = r3.json()
        r = httpx.post(
            f"{API_BASE_URL}/api/abas/reorder",
            json={"ordered_ids": [aba3["id"], aba2["id"]]},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 2
        r = httpx.get(f"{API_BASE_URL}/api/abas/me", headers=h, timeout=5)
        items = r.json()["items"]
        assert items[0]["id"] == aba3["id"], "reorder não respeitado"
        assert items[1]["id"] == aba2["id"]


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Garantia crítica: aba de um user NÃO é visível pra outro."""

    def test_aba_de_outro_user_nao_aparece(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        # Cria segundo user na MESMA empresa
        other_user = f"test-aba-other-{_RUN}"
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth."user" (id, name, email, "emailVerified",
                                              "createdAt", "updatedAt", status,
                                              is_superadmin)
                    VALUES (%s, 'Other User', %s, TRUE,
                            NOW(), NOW(), 'active', FALSE)
                    """,
                    (other_user, f"{other_user}@e2e.test"),
                )
                cur.execute(
                    """
                    INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                    VALUES (%s, %s, 'admin', TRUE)
                    """,
                    (empresa_id, other_user),
                )
                # Mesmo perfil Admin → outras perms iguais
                cur.execute(
                    "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                    (empresa_id,),
                )
                pf_row = cur.fetchone()
                if pf_row:
                    cur.execute(
                        """
                        INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                                    assigned_by_user_id)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (other_user, int(pf_row[0]), empresa_id, admin_user_id),
                    )

        try:
            # User original cria uma aba "Privada"
            r = httpx.post(
                f"{API_BASE_URL}/api/abas",
                json={"descricao": f"Privada {_RUN}", "cor": "#ff0000"},
                headers=_headers(admin_user_id, empresa_id),
                timeout=5,
            )
            assert r.status_code == 200, r.text
            aba_privada = r.json()

            # Other user lista — não vê
            r = httpx.get(
                f"{API_BASE_URL}/api/abas/me",
                headers=_headers(other_user, empresa_id),
                timeout=5,
            )
            assert r.status_code == 200, r.text
            other_items = r.json()["items"]
            assert all(a["id"] != aba_privada["id"] for a in other_items), (
                "User vê aba de outro user!"
            )

            # Other user tenta editar aba alheia → 404
            r = httpx.patch(
                f"{API_BASE_URL}/api/abas/{aba_privada['id']}",
                json={"descricao": "Hijack"},
                headers=_headers(other_user, empresa_id),
                timeout=5,
            )
            assert r.status_code == 404, "PATCH cross-user deve dar 404"

            # Other user tenta deletar aba alheia → 404
            r = httpx.delete(
                f"{API_BASE_URL}/api/abas/{aba_privada['id']}",
                headers=_headers(other_user, empresa_id),
                timeout=5,
            )
            assert r.status_code == 404, "DELETE cross-user deve dar 404"

            # Aba original ainda existe
            r = httpx.get(
                f"{API_BASE_URL}/api/abas/me",
                headers=_headers(admin_user_id, empresa_id),
                timeout=5,
            )
            descs = [a["descricao"] for a in r.json()["items"]]
            assert f"Privada {_RUN}" in descs, (
                "aba do owner foi modificada por outro user!"
            )
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        'DELETE FROM auth."user" WHERE id = %s', (other_user,)
                    )
