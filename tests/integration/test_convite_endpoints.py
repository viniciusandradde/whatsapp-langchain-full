"""Smoke + E2E do convite de acesso por WhatsApp (mig 167).

Smoke (sem DB): rota existe e exige service token. Roda em CI.
E2E (stack real): sem telefone → ok:false com motivo; sem conexão → idem;
telefone + conexão (Evolution em modo mock no dev) → ok:true e
`convite_enviado_at` gravado. Isolamento: admin sem `empresa.member.add` → 403.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_convite_endpoints.py -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

LINK = "https://painel.example/reset-password?token=e2e-{run}"

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_convite_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/usuarios/abc/convite",
            json={"link": "https://x/reset", "expira_em": "2026-01-01T00:00:00Z"},
        )
        assert r.status_code == 401

    def test_rota_registrada(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/usuarios/{user_id}/convite" in rotas

    def test_criar_usuario_sem_auth_401(self) -> None:
        assert _client().post("/api/usuarios", json={"nome": "X"}).status_code == 401


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


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            -- Pro (10 usuários): o Free para em 2 desde a ADR-005 leva A
            VALUES (%s, %s, 'pro', 'active')
            RETURNING id
            """,
            (f"test-convite-{_RUN}", f"test-convite-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _criar_user(
    db_url: str,
    empresa_id: int,
    sufixo: str,
    *,
    telefone: str | None,
    superadmin: bool = True,
) -> str:
    uid = f"test-convite-{sufixo}-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, telefone, "emailVerified",
                                     "createdAt", "updatedAt", status,
                                     is_superadmin)
            VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW(), 'active', %s)
            """,
            (uid, f"Convite {sufixo}", f"{uid}@e2e.test", telefone, superadmin),
        )
        cur.execute(
            """
            INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
            VALUES (%s, %s, 'admin', TRUE)
            """,
            (empresa_id, uid),
        )
    return uid


@pytest.fixture(scope="module")
def admin_id(db_url: str, empresa_id: int):
    uid = _criar_user(db_url, empresa_id, "admin", telefone=None)
    yield uid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))


@pytest.fixture(scope="module")
def alvo_sem_telefone_id(db_url: str, empresa_id: int):
    uid = _criar_user(db_url, empresa_id, "semtel", telefone=None, superadmin=False)
    yield uid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))


@pytest.fixture(scope="module")
def alvo_com_telefone_id(db_url: str, empresa_id: int):
    uid = _criar_user(
        db_url, empresa_id, "comtel", telefone="+5567999880034", superadmin=False
    )
    yield uid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


def _post_convite(user_id: str, headers: dict[str, str]) -> httpx.Response:
    return httpx.post(
        f"{API_BASE_URL}/api/usuarios/{user_id}/convite",
        headers=headers,
        json={
            "link": LINK.format(run=_RUN),
            "expira_em": "2026-12-31T12:00:00Z",
        },
        timeout=30,
    )


@pytest.mark.docker_demo
class TestE2E:
    def test_1_sem_telefone_explica(
        self, admin_id: str, empresa_id: int, alvo_sem_telefone_id: str
    ) -> None:
        r = _post_convite(alvo_sem_telefone_id, _headers(admin_id, empresa_id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert "WhatsApp cadastrado" in body["erro"]
        # O link JAMAIS volta na resposta
        assert _RUN not in body.get("erro", "")

    def test_2_sem_conexao_explica(
        self, admin_id: str, empresa_id: int, alvo_com_telefone_id: str
    ) -> None:
        """Empresa de teste nasce sem conexão — o motivo tem que dizer isso."""
        r = _post_convite(alvo_com_telefone_id, _headers(admin_id, empresa_id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert "conexão" in body["erro"].lower()

    def test_3_com_conexao_envia_e_grava_data(
        self,
        db_url: str,
        admin_id: str,
        empresa_id: int,
        alvo_com_telefone_id: str,
    ) -> None:
        """Com conexão ativa (Evolution mock no dev), o convite sai e
        `convite_enviado_at` é gravado."""
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT set_config('app.bypass_rls', 'on', false)")
            # instance_name é obrigatório pro EvolutionClient; sem ele o
            # build_outbound_client recusa com "Evolution não configurada".
            # Em EVOLUTION_OUTBOUND_MODE=mock (dev) o envio só loga.
            cur.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                     display_name, status, is_default,
                                     payload_json)
                VALUES (%s, 'evolution', %s, 'E2E Convite', 'active', TRUE,
                        %s::jsonb)
                RETURNING id
                """,
                (
                    empresa_id,
                    f"+55679{_RUN[:8]}",
                    f'{{"instance_name": "e2e-convite-{_RUN}"}}',
                ),
            )
        r = _post_convite(alvo_com_telefone_id, _headers(admin_id, empresa_id))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True, body
        assert body["telefone"] == "+5567999880034"
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                'SELECT convite_enviado_at FROM auth."user" WHERE id = %s',
                (alvo_com_telefone_id,),
            )
            row = cur.fetchone()
        assert row is not None and row[0] is not None

    def test_4_listagem_expoe_convite_enviado_at(
        self, admin_id: str, empresa_id: int, alvo_com_telefone_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/usuarios",
            headers=_headers(admin_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        alvo = [u for u in r.json()["items"] if u["id"] == alvo_com_telefone_id]
        assert alvo, "usuário alvo não veio na listagem"
        assert alvo[0]["convite_enviado_at"] is not None

    def test_5_telefone_invalido_no_cadastro_da_400(
        self, admin_id: str, empresa_id: int
    ) -> None:
        """O caso real da empresa 1: número com + mas sem DDD é recusado na
        ENTRADA, com frase legível — não vira falha de envio um mês depois."""
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            headers=_headers(admin_id, empresa_id),
            json={"nome": f"Tel Invalido {_RUN}", "telefone": "+55996460034"},
            timeout=30,
        )
        assert r.status_code == 400, r.text
        assert "DDD" in r.json()["detail"]


@pytest.mark.docker_demo
class TestE2EIsolamento:
    def test_sem_permissao_403(
        self, db_url: str, empresa_id: int, alvo_com_telefone_id: str
    ) -> None:
        """Usuário comum (sem empresa.member.add) não dispara convite."""
        uid = _criar_user(db_url, empresa_id, "comum", telefone=None, superadmin=False)
        try:
            r = _post_convite(alvo_com_telefone_id, _headers(uid, empresa_id))
            assert r.status_code == 403, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))
