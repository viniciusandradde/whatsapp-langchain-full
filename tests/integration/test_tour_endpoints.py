"""Smoke + E2E do guia de primeiro acesso (mig 171).

O guia é do USUÁRIO (não da empresa, como o `/onboarding`): marca em
`auth."user".tour_operador_at` e nunca mais aparece.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_get_tour_sem_auth_401(self) -> None:
        assert _client().get("/api/usuarios/me/tour").status_code == 401

    def test_post_tour_sem_auth_401(self) -> None:
        assert _client().post("/api/usuarios/me/tour").status_code == 401


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def user_id(self):
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        uid = f"test-tour-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Tour', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (uid, f"{uid}@e2e.test"),
        )
        yield uid
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))
        conn.close()

    def _h(self, uid: str) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = uid
        h["X-Empresa-Id"] = "1"
        return h

    def test_1_usuario_novo_ainda_nao_viu(self, user_id) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/usuarios/me/tour",
            headers=self._h(user_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["visto"] is False

    def test_2_marca_e_nao_volta(self, user_id) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios/me/tour",
            headers=self._h(user_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        r2 = httpx.get(
            f"{API_BASE_URL}/api/usuarios/me/tour",
            headers=self._h(user_id),
            timeout=30,
        )
        assert r2.json()["visto"] is True

    def test_3_marcar_de_novo_preserva_a_primeira_data(self, user_id) -> None:
        # `COALESCE`: rever o guia não reescreve quando a pessoa viu a 1ª vez.
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            'SELECT tour_operador_at FROM auth."user" WHERE id = %s', (user_id,)
        )
        antes = cur.fetchone()[0]
        httpx.post(
            f"{API_BASE_URL}/api/usuarios/me/tour",
            headers=self._h(user_id),
            timeout=30,
        )
        cur.execute(
            'SELECT tour_operador_at FROM auth."user" WHERE id = %s', (user_id,)
        )
        depois = cur.fetchone()[0]
        conn.close()
        assert antes == depois
