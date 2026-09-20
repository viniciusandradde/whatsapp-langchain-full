"""Smoke + E2E da leva C2 da ADR-005 (mig 192): quantidades e retenção por
plano — departamentos, workflows ativos, menus, retenção, janela de
auditoria, CSAT, resumo diário, bateria de testes, fila/traces
(observabilidade) e relatórios de qualidade da IA.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_c2_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import (
    _criar_empresa,
    _dar_perfil_admin,
    _esperar_cache_do_plano,
    _flag,
    _headers,
)


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    @pytest.mark.parametrize(
        ("metodo", "caminho"),
        [
            ("POST", "/api/departamentos"),
            ("POST", "/api/admin/workflows/1/toggle-active"),
            ("POST", "/api/v1/menus"),
            ("GET", "/api/v1/audit"),
            ("GET", "/api/traces"),
            ("PUT", "/api/empresas/1/csat"),
            ("PUT", "/api/empresas/1/resumo-diario"),
            ("POST", "/api/v1/agentes/x/testar-bateria"),
        ],
    )
    def test_rotas_gateadas_exigem_auth(self, metodo: str, caminho: str) -> None:
        resp = _client().request(metodo, caminho)
        assert resp.status_code == 401, (caminho, resp.text)


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


def _apagar_empresa(db_url: str, eid: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-c2-pro-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-c2-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Leva C2', %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        _dar_perfil_admin(cur, empresa_id, user_id)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_free_id(db_url: str, admin_user_id: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "free", f"test-leva-c2-free-{_RUN}")
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', FALSE)",
            (eid, admin_user_id),
        )
        _dar_perfil_admin(cur, eid, admin_user_id)
    yield eid
    _apagar_empresa(db_url, eid)


def _402(r: httpx.Response) -> dict:
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert "_" not in d["message"], d["message"]  # texto de usuário final
    return d


@pytest.mark.docker_demo
class TestE2E:
    def test_01_departamentos_e_menus_no_free(
        self, db_url: str, empresa_free_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/departamentos",
            headers=hf,
            json={"nome": "Vendas"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        d = _402(
            httpx.post(
                f"{API_BASE_URL}/api/departamentos",
                headers=hf,
                json={"nome": "Suporte"},
                timeout=15,
            )
        )
        assert d["recurso"] == "departamentos" and d["quota_max"] == 1
        assert "departamentos" in d["message"]
        # menus_max = 1 no Free
        menu = {
            "nome": f"Menu {_RUN}",
            "mensagem_boas_vindas": "Olá! Escolha uma opção.",
        }
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/menus", headers=hf, json=menu, timeout=15
        )
        assert r.status_code == 201, r.text
        assert (
            _402(
                httpx.post(
                    f"{API_BASE_URL}/api/v1/menus", headers=hf, json=menu, timeout=15
                )
            )["recurso"]
            == "menus"
        )
        # grandfathering: departamentos ilimitados por flag
        _flag(db_url, empresa_free_id, "departamentos_max", "null")
        _esperar_cache_do_plano()
        try:
            r = httpx.post(
                f"{API_BASE_URL}/api/departamentos",
                headers=hf,
                json={"nome": "Suporte"},
                timeout=15,
            )
            assert r.status_code == 201, r.text
        finally:
            _flag(db_url, empresa_free_id, "departamentos_max", None)

    def test_02_workflow_ativar_no_free_402(
        self, db_url: str, empresa_free_id: int, admin_user_id: str
    ) -> None:
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workflow_chatbot (empresa_id, slug, nome, ativo, definicao) "
                "VALUES (%s, %s, 'WF', FALSE, '{}'::jsonb) RETURNING id",
                (empresa_free_id, f"wf-{_RUN}"),
            )
            wid = cur.fetchone()[0]  # type: ignore[index]
        hf = _headers(admin_user_id, empresa_free_id)
        d = _402(
            httpx.post(
                f"{API_BASE_URL}/api/admin/workflows/{wid}/toggle-active",
                headers=hf,
                timeout=15,
            )
        )
        assert d["recurso"] == "workflows" and d["quota_max"] == 0

    def test_03_retencao_csat_resumo_no_free(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        d = _402(
            httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
                headers=hf,
                json={"retencao_dias": 120},
                timeout=15,
            )
        )
        assert "30 dias" in d["message"]
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
            headers=hf,
            json={"retencao_dias": 30},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        csat = {
            "csat_ativo": True,
            "csat_pergunta": "De 0 a 10?",
            "csat_msg_agradecimento": "Obrigado",
            "csat_solicita_comentario": False,
        }
        assert (
            _402(
                httpx.put(
                    f"{API_BASE_URL}/api/empresas/{empresa_free_id}/csat",
                    headers=hf,
                    json=csat,
                    timeout=15,
                )
            )["feature"]
            == "csat"
        )
        resumo = {
            "resumo_diario_ativo": True,
            "resumo_diario_telefone": "+5567999000000",
            "resumo_diario_horario": "22:30",
            "resumo_diario_dias": [1, 2, 3, 4, 5],
            "resumo_diario_tz": "America/Campo_Grande",
        }
        assert (
            _402(
                httpx.put(
                    f"{API_BASE_URL}/api/empresas/{empresa_free_id}/resumo-diario",
                    headers=hf,
                    json=resumo,
                    timeout=15,
                )
            )["feature"]
            == "resumo_diario"
        )
        # Pro passa nos três
        hp = _headers(admin_user_id, empresa_id)
        assert (
            httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_id}",
                headers=hp,
                json={"retencao_dias": 120},
                timeout=15,
            ).status_code
            == 200
        )
        assert (
            httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_id}/csat",
                headers=hp,
                json=csat,
                timeout=15,
            ).status_code
            == 200
        )

    def test_04_observabilidade_qualidade_bateria(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        assert (
            _402(httpx.get(f"{API_BASE_URL}/api/traces", headers=hf, timeout=15))[
                "feature"
            ]
            == "observabilidade"
        )
        slug = f"c2-{_RUN}"
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=hf,
            json={"slug": slug, "nome": "C2", "template_catalog": "agente"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        d = _402(
            httpx.post(
                f"{API_BASE_URL}/api/v1/agentes/{slug}/testar-bateria",
                headers=hf,
                json={},
                timeout=15,
            )
        )
        assert d["feature"] == "bateria_testes"
        hp = _headers(admin_user_id, empresa_id)
        assert (
            httpx.get(f"{API_BASE_URL}/api/traces", headers=hp, timeout=15).status_code
            != 402
        )

    def test_05_auditoria_janela_por_plano(
        self, empresa_free_id: int, admin_user_id: str
    ) -> None:
        # Sem 402: a lista só para no teto (30 dias no Free) — aqui basta 200.
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/audit",
            headers=_headers(admin_user_id, empresa_free_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
