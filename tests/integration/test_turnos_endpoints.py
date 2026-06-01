"""Sprint U (Fase 2) — E2E dos endpoints /api/turnos.

Smoke vive em tests/unit/test_turnos_endpoints_smoke.py (CI).
E2E (`docker_demo`): criar→atualizar→atribuir usuários→listar→deletar
em empresa isolada. Requer make up.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_turnos_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

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
        pytest.skip("DB não acessível.")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"test-turno-{_RUN}", f"test-turno-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    user_id = f"test-turno-admin-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            'INSERT INTO auth."user" (id, name, email, "emailVerified", '
            '"createdAt", "updatedAt", status, is_superadmin) '
            "VALUES (%s, 'Admin Turno', %s, TRUE, NOW(), NOW(), 'active', TRUE)",
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
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
    def test_fluxo_turno(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _h(admin_user_id, empresa_id)

        # criar com 2 janelas
        r = httpx.post(
            f"{API_BASE_URL}/api/turnos",
            json={
                "nome": f"Comercial {_RUN}",
                "horarios": [
                    {"dia_semana": 1, "hora_inicio": "08:00", "hora_fim": "12:00"},
                    {"dia_semana": 1, "hora_inicio": "13:00", "hora_fim": "18:00"},
                ],
            },
            headers=h,
            timeout=10,
        )
        assert r.status_code == 201, r.text
        turno = r.json()
        tid = turno["id"]
        assert len(turno["horarios"]) == 2

        try:
            # validação: fim <= início → 422
            r = httpx.post(
                f"{API_BASE_URL}/api/turnos",
                json={
                    "nome": f"Ruim {_RUN}",
                    "horarios": [
                        {"dia_semana": 0, "hora_inicio": "18:00", "hora_fim": "08:00"}
                    ],
                },
                headers=h,
                timeout=10,
            )
            assert r.status_code == 422, r.text

            # atualizar nome + substituir horários
            r = httpx.put(
                f"{API_BASE_URL}/api/turnos/{tid}",
                json={
                    "nome": f"Comercial {_RUN} v2",
                    "horarios": [
                        {"dia_semana": 2, "hora_inicio": "09:00", "hora_fim": "17:00"}
                    ],
                },
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json()["nome"] == f"Comercial {_RUN} v2"
            assert len(r.json()["horarios"]) == 1

            # atribuir o admin ao turno
            r = httpx.put(
                f"{API_BASE_URL}/api/turnos/{tid}/users",
                json={"user_ids": [admin_user_id]},
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text

            r = httpx.get(
                f"{API_BASE_URL}/api/turnos/{tid}/users", headers=h, timeout=10
            )
            assert r.status_code == 200, r.text
            assert any(u["id"] == admin_user_id for u in r.json()["users"])

            # lista mostra users_count=1
            r = httpx.get(f"{API_BASE_URL}/api/turnos", headers=h, timeout=10)
            assert r.status_code == 200, r.text
            achado = next(t for t in r.json()["items"] if t["id"] == tid)
            assert achado["users_count"] == 1

        finally:
            r = httpx.delete(
                f"{API_BASE_URL}/api/turnos/{tid}", headers=h, timeout=10
            )
            assert r.status_code == 204, r.text
            r = httpx.get(
                f"{API_BASE_URL}/api/turnos/{tid}", headers=h, timeout=10
            )
            assert r.status_code == 404
