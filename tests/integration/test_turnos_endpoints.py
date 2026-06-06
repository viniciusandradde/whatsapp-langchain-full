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
            r = httpx.delete(f"{API_BASE_URL}/api/turnos/{tid}", headers=h, timeout=10)
            assert r.status_code == 204, r.text
            r = httpx.get(f"{API_BASE_URL}/api/turnos/{tid}", headers=h, timeout=10)
            assert r.status_code == 404


@pytest.mark.docker_demo
class TestE2EGateDistribuicao:
    """Valida a SEMÂNTICA do gate de distribuição por turno (SQL de prod).

    Importa `turno_gate_sql` (usado no `pick_best_atendente`) e exercita o
    fragmento contra dados controlados — determinístico (dia/hora explícitos,
    sem depender do relógio). `postgres` superuser bypassa RLS.
    """

    def test_gate_semantica(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        from whatsapp_langchain.shared.turno import turno_gate_sql

        gate_expr = turno_gate_sql("u")
        sql = f'SELECT {gate_expr} FROM auth."user" u WHERE u.id = %s'

        def eligivel(uid: str, dia: int, hora: str) -> bool:
            with psycopg.connect(db_url) as conn, conn.cursor() as cur:
                cur.execute(sql, (empresa_id, empresa_id, dia, hora, hora, uid))
                row = cur.fetchone()
                assert row is not None
                return bool(row[0])

        # turno "GateTest": Seg (dia 1) 08:00–12:00, atribuído ao admin
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO turno (empresa_id, nome, ativo) "
                "VALUES (%s, 'GateTest', TRUE) RETURNING id",
                (empresa_id,),
            )
            row = cur.fetchone()
            assert row is not None
            tid = int(row[0])
            cur.execute(
                "INSERT INTO turno_horario "
                "(turno_id, dia_semana, hora_inicio, hora_fim) "
                "VALUES (%s, 1, '08:00', '12:00')",
                (tid,),
            )
            cur.execute(
                "INSERT INTO usuario_turno (user_id, turno_id, empresa_id) "
                "VALUES (%s, %s, %s)",
                (admin_user_id, tid, empresa_id),
            )

        other = f"test-gate-noturno-{_RUN}"
        try:
            # dentro da janela (Seg 10:00) → elegível
            assert eligivel(admin_user_id, 1, "10:00") is True
            # fora da janela (Seg 20:00) → bloqueado
            assert eligivel(admin_user_id, 1, "20:00") is False
            # outro dia (Dom 10:00) → bloqueado
            assert eligivel(admin_user_id, 0, "10:00") is False
            # borda: hora_fim é exclusiva (12:00 não conta)
            assert eligivel(admin_user_id, 1, "12:00") is False

            # usuário SEM turno atribuído → irrestrito (sempre elegível)
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO auth."user" (id, name, email, "emailVerified", '
                    '"createdAt", "updatedAt", status, is_superadmin) '
                    "VALUES (%s, 'NoTurno', %s, TRUE, NOW(), NOW(), 'active', FALSE)",
                    (other, f"{other}@e2e.test"),
                )
                cur.execute(
                    "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
                    "VALUES (%s, %s, 'operator', FALSE)",
                    (empresa_id, other),
                )
            assert eligivel(other, 0, "03:00") is True

            # turno inativo não conta como restrição (volta a irrestrito)
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute("UPDATE turno SET ativo = FALSE WHERE id = %s", (tid,))
            assert eligivel(admin_user_id, 0, "03:00") is True
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (other,))
                cur.execute("DELETE FROM turno WHERE id = %s", (tid,))
