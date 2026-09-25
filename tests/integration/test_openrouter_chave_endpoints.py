"""Smoke + E2E da chave da OpenRouter por empresa (ADR-007, mig 204):
`GET/PUT/DELETE /api/empresas/{id}/openrouter-chave`, `POST …/provisionar`
e `PUT …/limite`.

O E2E não usa chave real: a validação de uma chave que a empresa traz é
feita contra a OpenRouter de verdade com uma chave FALSA (a OpenRouter
responde 401 → a rota devolve 422), e o estado "definida" é semeado direto
no banco com a mesma cifra do dev (Fernet derivada do INTERNAL_SERVICE_TOKEN).

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_openrouter_chave_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import _criar_empresa, _dar_perfil_admin, _headers
from .test_plano_leva_e_endpoints import _criar_user

_RUN = uuid.uuid4().hex[:8]
_CHAVE_FALSA = "sk-or-v1-" + "0" * 64


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    @pytest.mark.parametrize(
        ("metodo", "caminho"),
        [
            ("GET", "/api/empresas/1/openrouter-chave"),
            ("PUT", "/api/empresas/1/openrouter-chave"),
            ("DELETE", "/api/empresas/1/openrouter-chave"),
            ("POST", "/api/empresas/1/openrouter-chave/provisionar"),
            ("PUT", "/api/empresas/1/openrouter-chave/limite"),
        ],
    )
    def test_rotas_exigem_auth(self, metodo: str, caminho: str) -> None:
        resp = _client().request(metodo, caminho)
        assert resp.status_code == 401, (caminho, resp.text)


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


def _apagar_empresa(db_url: str, eid: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM audit_log WHERE empresa_id = %s", (eid,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _apagar_user(db_url: str, user_id: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_a(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-orkey-a-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def empresa_b(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-orkey-b-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


def _membro(
    db_url: str, empresa_id: int, user_id: str, role: str, *, perfil_admin: bool
):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=False)
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, %s, TRUE)",
            (empresa_id, user_id, role),
        )
        if perfil_admin:
            _dar_perfil_admin(cur, empresa_id, user_id)


@pytest.fixture(scope="module")
def admin_a(db_url: str, empresa_a: int):
    uid = f"test-orkey-admin-a-{_RUN}"
    _membro(db_url, empresa_a, uid, "admin", perfil_admin=True)
    yield uid
    _apagar_user(db_url, uid)


@pytest.fixture(scope="module")
def operador_a(db_url: str, empresa_a: int):
    uid = f"test-orkey-oper-a-{_RUN}"
    _membro(db_url, empresa_a, uid, "operator", perfil_admin=False)
    yield uid
    _apagar_user(db_url, uid)


@pytest.fixture(scope="module")
def admin_b(db_url: str, empresa_b: int):
    uid = f"test-orkey-admin-b-{_RUN}"
    _membro(db_url, empresa_b, uid, "admin", perfil_admin=True)
    yield uid
    _apagar_user(db_url, uid)


@pytest.fixture(scope="module")
def superadmin(db_url: str):
    uid = f"test-orkey-super-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, uid, superadmin=True)
    yield uid
    _apagar_user(db_url, uid)


def _semear_chave(
    db_url: str, empresa_id: int, chave: str, origem: str, hash_: str | None
) -> None:
    """Grava a chave cifrada como a API gravaria (mesma cifra do dev)."""
    from whatsapp_langchain.integrations.crypto import encrypt_str
    from whatsapp_langchain.integrations.openrouter_gestao import mascarar

    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE empresa
               SET openrouter_chave_cifrada = %s, openrouter_chave_prefixo = %s,
                   openrouter_chave_origem = %s, openrouter_chave_hash = %s,
                   openrouter_chave_definida_em = NOW()
             WHERE id = %s
            """,
            (encrypt_str(chave), mascarar(chave), origem, hash_, empresa_id),
        )


@pytest.mark.docker_demo
class TestE2EChaveOpenRouter:
    def test_01_sem_chave_o_status_diz_plataforma(self, empresa_a, admin_a):
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["definida"] is False
        assert body["origem"] is None
        assert body["prefixo"] is None
        assert "chave" not in body

    def test_02_operador_nao_ve_nem_define(self, empresa_a, operador_a):
        h = _headers(operador_a, empresa_a)
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=h,
            timeout=15,
        )
        assert r.status_code == 403, r.text
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=h,
            json={"chave": _CHAVE_FALSA},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_03_admin_de_outra_empresa_nao_ve(self, empresa_a, empresa_b, admin_b):
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_b, empresa_b),
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_04_formato_errado_e_422_sem_ir_a_rede(self, empresa_a, admin_a):
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            json={"chave": "EAAG" + "x" * 60},
            timeout=15,
        )
        assert r.status_code == 422, r.text
        assert "sk-or-" in r.json()["detail"]

    def test_05_chave_falsa_e_recusada_pela_openrouter(self, empresa_a, admin_a):
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            json={"chave": _CHAVE_FALSA},
            timeout=40,
        )
        # 422 = a OpenRouter respondeu 401 (chave inexistente); 502 só se o
        # dev estiver sem saída para a internet.
        assert r.status_code in (422, 502), r.text
        if r.status_code == 422:
            assert "não reconheceu" in r.json()["detail"]
        # Nada gravado.
        s = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            timeout=15,
        ).json()
        assert s["definida"] is False

    def test_06_status_de_chave_propria_semeada(self, db_url, empresa_a, admin_a):
        _semear_chave(db_url, empresa_a, _CHAVE_FALSA, "propria", None)
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            timeout=40,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["definida"] is True
        assert body["origem"] == "propria"
        assert body["prefixo"] == "sk-or-v1-000…"
        assert body["definida_em"]
        # A chave falsa não existe na OpenRouter: o uso vem vazio com aviso.
        assert body["uso"] is None
        assert body["uso_erro"]
        assert _CHAVE_FALSA not in r.text

    def test_07_provisionar_exige_superadmin_e_configuracao(
        self, empresa_a, admin_a, superadmin
    ):
        url = f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave/provisionar"
        r = httpx.post(
            url,
            headers=_headers(admin_a, empresa_a),
            json={"limite_usd": 10},
            timeout=15,
        )
        assert r.status_code == 403, r.text
        r = httpx.post(
            url,
            headers=_headers(superadmin, empresa_a),
            json={"limite_usd": 10},
            timeout=15,
        )
        # O dev não tem OPENROUTER_PROVISIONING_KEY: 409 explicando.
        assert r.status_code in (409, 201), r.text
        if r.status_code == 409:
            assert "provisionamento" in r.json()["detail"].lower()

    def test_08_limite_so_em_chave_provisionada(self, empresa_a, superadmin):
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave/limite",
            headers=_headers(superadmin, empresa_a),
            json={"limite_usd": 5},
            timeout=15,
        )
        assert r.status_code == 409, r.text

    def test_09_provisionada_so_superadmin_remove(
        self, db_url, empresa_a, admin_a, superadmin
    ):
        _semear_chave(db_url, empresa_a, _CHAVE_FALSA, "provisionada", "hash-falso")
        r = httpx.delete(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            timeout=15,
        )
        assert r.status_code == 403, r.text
        r = httpx.delete(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(superadmin, empresa_a),
            timeout=40,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["definida"] is False
        # Sem chave de gestão no dev a OpenRouter não é chamada: fica False.
        assert body["apagada_na_openrouter"] in (False, True)

    def test_10_admin_remove_a_propria(self, db_url, empresa_a, admin_a):
        _semear_chave(db_url, empresa_a, _CHAVE_FALSA, "propria", None)
        r = httpx.delete(
            f"{API_BASE_URL}/api/empresas/{empresa_a}/openrouter-chave",
            headers=_headers(admin_a, empresa_a),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["definida"] is False
        assert r.json()["apagada_na_openrouter"] is None
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT openrouter_chave_cifrada, openrouter_chave_origem FROM empresa WHERE id = %s",
                (empresa_a,),
            )
            assert cur.fetchone() == (None, None)

    def test_11_auditoria_sem_a_chave(self, db_url, empresa_a):
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT action, payload_diff::text FROM audit_log "
                "WHERE empresa_id = %s AND action LIKE 'openrouter.%%' ORDER BY id",
                (empresa_a,),
            )
            rows = cur.fetchall()
        acoes = [r[0] for r in rows]
        assert "openrouter.chave_removida" in acoes
        assert all(_CHAVE_FALSA not in (r[1] or "") for r in rows)
