"""Smoke + E2E dos endpoints de nota interna + marcar-lido (Sprint 1.3).

Modelo canônico: tests/integration/test_aba_endpoints.py.
"""

from __future__ import annotations

import time
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
# Smoke
# ============================================================================


class TestSmoke:
    def test_nota_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/atendimentos/1/nota", json={"texto": "x"}
        )
        assert resp.status_code == 401

    def test_marcar_lido_sem_auth_401(self) -> None:
        assert (
            _client().post("/api/atendimentos/1/marcar-lido").status_code == 401
        )


# ============================================================================
# E2E
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
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível.")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-nota-{_RUN}", f"test-nota-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    # message_queue tem FK não-cascade pra empresa — limpa explicitamente
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (eid,))
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    user_id = f"test-nota-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Nota E2E', %s, TRUE, NOW(), NOW(),
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
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                      display_name, status)
                VALUES (%s, 'twilio_sandbox', %s, %s, 'active')
                RETURNING id
                """,
                (empresa_id, f"+155502{_RUN[:5]}", f"conn-nota-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            cid = int(row[0])
            cur.execute(
                """
                INSERT INTO cliente (empresa_id, telefone, nome, status)
                VALUES (%s, %s, 'Cliente Nota', 'active')
                RETURNING id
                """,
                (empresa_id, f"+5511991{_RUN[:5]}"),
            )
            row = cur.fetchone()
            assert row is not None
            cli_id = int(row[0])
            cur.execute(
                """
                INSERT INTO atendimento (empresa_id, cliente_id, conexao_id,
                                          status, last_message_at)
                VALUES (%s, %s, %s, 'em_andamento', NOW())
                RETURNING id
                """,
                (empresa_id, cli_id, cid),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo: criar nota → aparece no /mensagens → não vai pra fila outbound."""

    def test_fluxo_completo_nota_interna(
        self, db_url: str, empresa_id: int, admin_user_id: str, atendimento_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)

        # --- 1. POST /nota cria msg interna
        texto = f"Cliente confirmou agendamento por telefone {_RUN}"
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/nota",
            json={"texto": texto},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["interna"] is True
        assert body["criado_por_user_id"] == admin_user_id
        assert body["response"] == texto
        msg_id = body["id"]

        # --- 2. Verifica no DB: status='done', interna=true, criado_por_user_id
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, interna, criado_por_user_id, response
                      FROM message_queue WHERE id = %s
                    """,
                    (msg_id,),
                )
                row = cur.fetchone()
        assert row is not None
        status, interna, criado_por, response = row
        assert status == "done", "nota NÃO deve entrar como queued"
        assert interna is True
        assert criado_por == admin_user_id
        assert response == texto

        # --- 3. GET /mensagens retorna a nota com flag interna=true
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/mensagens",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        msgs = r.json()["mensagens"]
        nota = next((m for m in msgs if m["id"] == msg_id), None)
        assert nota is not None
        assert nota["interna"] is True
        assert nota["criado_por_user_id"] == admin_user_id
        assert nota["response"] == texto

        # --- 4. Worker NÃO pega a nota (status='done', não 'queued')
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM message_queue
                     WHERE id = %s AND status = 'queued'
                    """,
                    (msg_id,),
                )
                row = cur.fetchone()
                assert row is not None and row[0] == 0

        # --- 5. Texto inválido (vazio) → 422
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/nota",
            json={"texto": ""},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 422

        # --- 6. Atendimento de outra empresa → 403
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/99999999/nota",
            json={"texto": "Hijack"},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404

        # --- 7. POST /marcar-lido cria UPSERT em atendimento_visualizacao
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/marcar-lido",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ultima_visualizacao_at FROM atendimento_visualizacao
                     WHERE atendimento_id = %s AND user_id = %s
                    """,
                    (atendimento_id, admin_user_id),
                )
                row = cur.fetchone()
                assert row is not None
                first_seen = row[0]

        # --- 8. Re-marcar atualiza timestamp (UPSERT idempotente)
        time.sleep(0.1)
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atendimento_id}/marcar-lido",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ultima_visualizacao_at FROM atendimento_visualizacao
                     WHERE atendimento_id = %s AND user_id = %s
                    """,
                    (atendimento_id, admin_user_id),
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0] > first_seen, "timestamp deve avançar no re-mark"

        # --- 9. Marcar-lido em atendimento de outra empresa → 404
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/99999999/marcar-lido",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Outra empresa NÃO consegue criar nota nem marcar-lido."""

    def test_nota_cross_empresa_404(self, db_url: str) -> None:
        # Cria 2 empresas com 1 atendimento em A; user B tenta criar nota em A
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active')
                    RETURNING id
                    """,
                    (f"test-nota-iso-A-{_RUN}", f"test-nota-iso-A-{_RUN}"),
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
                    (f"test-nota-iso-B-{_RUN}", f"test-nota-iso-B-{_RUN}"),
                )
                row_b = cur.fetchone()
                assert row_b is not None
                emp_b = int(row_b[0])

                user_b = f"test-nota-iso-b-{_RUN}"
                cur.execute(
                    """
                    INSERT INTO auth."user" (id, name, email, "emailVerified",
                                              "createdAt", "updatedAt", status,
                                              is_superadmin)
                    VALUES (%s, 'Iso B', %s, TRUE, NOW(), NOW(),
                            'active', FALSE)
                    """,
                    (user_b, f"{user_b}@iso.test"),
                )
                cur.execute(
                    """
                    INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                    VALUES (%s, %s, 'admin', TRUE)
                    """,
                    (emp_b, user_b),
                )
                cur.execute(
                    """
                    INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                    VALUES (%s, 'Admin', 'Acesso total', TRUE)
                    ON CONFLICT (empresa_id, nome) DO NOTHING
                    RETURNING id
                    """,
                    (emp_b,),
                )
                prow = cur.fetchone()
                if prow is None:
                    cur.execute(
                        "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                        (emp_b,),
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
                    (user_b, pf_id, emp_b, user_b),
                )
                # Atendimento em A
                cur.execute(
                    """
                    INSERT INTO conexao (empresa_id, provider, from_number,
                                          display_name, status)
                    VALUES (%s, 'twilio_sandbox', %s, %s, 'active')
                    RETURNING id
                    """,
                    (emp_a, f"+155503{_RUN[:5]}", f"conn-iso-{_RUN}"),
                )
                conn_row = cur.fetchone()
                assert conn_row is not None
                conex_id = int(conn_row[0])
                cur.execute(
                    """
                    INSERT INTO cliente (empresa_id, telefone, nome, status)
                    VALUES (%s, %s, 'Cliente A', 'active')
                    RETURNING id
                    """,
                    (emp_a, f"+5511992{_RUN[:5]}"),
                )
                cli_row = cur.fetchone()
                assert cli_row is not None
                cli_id = int(cli_row[0])
                cur.execute(
                    """
                    INSERT INTO atendimento (empresa_id, cliente_id, conexao_id,
                                              status, last_message_at)
                    VALUES (%s, %s, %s, 'em_andamento', NOW())
                    RETURNING id
                    """,
                    (emp_a, cli_id, conex_id),
                )
                atd_row = cur.fetchone()
                assert atd_row is not None
                atd_a = int(atd_row[0])

        try:
            # B (empresa B) tenta criar nota no atendimento de A → 404
            r = httpx.post(
                f"{API_BASE_URL}/api/atendimentos/{atd_a}/nota",
                json={"texto": "Hijack"},
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            # Helper _load_atendimento_in_empresa diferencia "não existe" (404)
            # de "existe mas de outra empresa" (403). Aqui é 403.
            assert r.status_code == 403, r.text

            # B tenta marcar-lido em atendimento de A → 403
            r = httpx.post(
                f"{API_BASE_URL}/api/atendimentos/{atd_a}/marcar-lido",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert r.status_code == 403

            # DB: nenhuma nota foi criada em A pelo user B
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM message_queue
                         WHERE atendimento_id = %s AND criado_por_user_id = %s
                        """,
                        (atd_a, user_b),
                    )
                    row = cur.fetchone()
                    assert row is not None and row[0] == 0
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM message_queue WHERE empresa_id IN (%s, %s)",
                        (emp_a, emp_b),
                    )
                    cur.execute(
                        "DELETE FROM empresa WHERE id IN (%s, %s)",
                        (emp_a, emp_b),
                    )
