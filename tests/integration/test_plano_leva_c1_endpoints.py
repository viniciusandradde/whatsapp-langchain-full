"""Smoke + E2E da leva C1 da ADR-005 (mig 191): módulos passam a depender do
plano — Disparador (campanhas/captura/extensão), perfis customizados (RBAC),
white-label, menu moderno, webhooks de saída e conexão WABA — e as feature
flags viram ferramenta de superadmin. MCP ficou FORA por decisão do dono
(20/09): a chave `mcp` segue só como dado.

Smoke (sem DB): as rotas existem e exigem service token.
E2E (stack rodando): Free, Pro e Enterprise com o MESMO admin (não
superadmin). Em cada gate: 402 `feature_unavailable` no plano sem a chave,
passa no plano com ela; grandfathering por flag `plano.<chave>` (D3). Onde
o gate é `Depends`, um id inexistente basta: 402 vem ANTES do 404.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_c1_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.shared.api_key import generate_api_key

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import (  # mesmas fixtures/helpers da leva A
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
            ("POST", "/api/campanhas"),
            ("POST", "/api/campanhas/1/clonar"),
            ("POST", "/api/conexoes/1/captura/contatos"),
            ("POST", "/api/perfis"),
            ("POST", "/api/hooks"),
            ("PUT", "/api/v1/menus/1"),
            ("PUT", "/api/empresas/1"),
            ("POST", "/api/empresas/1/logo"),
            ("POST", "/api/conexoes/waba/finalize"),
            ("GET", "/api/v1/feature-flags"),
        ],
    )
    def test_rotas_gateadas_exigem_auth(self, metodo: str, caminho: str) -> None:
        resp = _client().request(metodo, caminho)
        assert resp.status_code == 401, (caminho, resp.text)

    def test_extensao_sem_api_key_401(self) -> None:
        resp = _client().post("/api/captura/contatos", json={})
        assert resp.status_code in (401, 403), resp.text


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
    """Pro: disparador, rbac, webhooks, waba, menu_moderno — sem mcp/white_label."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-c1-pro-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-c1-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Leva C1', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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


def _empresa_extra(db_url: str, admin_user_id: str, slug_plano: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, slug_plano, f"test-leva-c1-{slug_plano}-{_RUN}")
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', FALSE)",
            (eid, admin_user_id),
        )
        _dar_perfil_admin(cur, eid, admin_user_id)
    return eid


@pytest.fixture(scope="module")
def empresa_free_id(db_url: str, admin_user_id: str):
    eid = _empresa_extra(db_url, admin_user_id, "free")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def empresa_ent_id(db_url: str, admin_user_id: str):
    eid = _empresa_extra(db_url, admin_user_id, "enterprise")
    yield eid
    _apagar_empresa(db_url, eid)


def _api_key(db_url: str, empresa_id: int) -> str:
    plain, prefix, key_hash = generate_api_key(empresa_id)
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO empresa_api_key (empresa_id, label, key_prefix, key_hash, scopes)
            VALUES (%s, %s, %s, %s, ARRAY['capture','dispatch'])
            """,
            (empresa_id, f"e2e-{prefix}", prefix, key_hash),
        )
    return plain


def _detail(r: httpx.Response) -> dict:
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["error"] == "feature_unavailable", d
    return d


@pytest.mark.docker_demo
class TestE2E:
    def test_01_disparador_campanhas_e_captura(
        self, db_url: str, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        # Depends → 402 antes do 404 do id inexistente.
        d = _detail(
            httpx.post(
                f"{API_BASE_URL}/api/campanhas/999999/clonar", headers=hf, timeout=15
            )
        )
        assert d["feature"] == "disparador" and d["upgrade_to"] == "pro"
        _detail(
            httpx.post(
                f"{API_BASE_URL}/api/campanhas/999999/dispatch", headers=hf, timeout=15
            )
        )
        _detail(
            httpx.post(
                f"{API_BASE_URL}/api/conexoes/999999/captura/contatos",
                headers=hf,
                timeout=15,
            )
        )
        # Pro passa o gate (e cai no 404 do id).
        hp = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/campanhas/999999/clonar", headers=hp, timeout=15
        )
        assert r.status_code == 404, r.text

    def test_02_extensao_com_api_key_do_free_402(
        self, db_url: str, empresa_free_id: int, empresa_id: int
    ) -> None:
        key_free = _api_key(db_url, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/captura/contatos",
            headers={"Authorization": f"Bearer {key_free}"},
            json={"contatos": [{"wa_jid": "5567999000001@s.whatsapp.net"}]},
            timeout=15,
        )
        d = _detail(r)
        assert d["feature"] == "disparador"
        assert "Disparador" in d["message"]
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/campanha",
            headers={"Authorization": f"Bearer {key_free}"},
            json={"nome": "x", "mensagem": "oi", "telefones": ["+5567999000001"]},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        # A mesma chamada com chave do Pro passa do gate de plano (o que vier
        # depois — validação do corpo — não é 402).
        key_pro = _api_key(db_url, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/captura/contatos",
            headers={"Authorization": f"Bearer {key_pro}"},
            json={"contatos": [{"wa_jid": "5567999000001@s.whatsapp.net"}]},
            timeout=15,
        )
        assert r.status_code != 402, r.text

    def test_04_perfis_customizados_e_webhooks(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        hp = _headers(admin_user_id, empresa_id)
        perfil = {"nome": f"Custom {_RUN}", "permissoes": ["atendimento.read"]}
        assert (
            _detail(
                httpx.post(
                    f"{API_BASE_URL}/api/perfis", headers=hf, json=perfil, timeout=15
                )
            )["feature"]
            == "rbac"
        )
        r = httpx.post(
            f"{API_BASE_URL}/api/perfis", headers=hp, json=perfil, timeout=15
        )
        assert r.status_code == 201, r.text

        hook = {
            "nome": "h",
            "evento": "atendimento.aberto",
            "url": "https://example.com/hook",
        }
        assert (
            _detail(
                httpx.post(
                    f"{API_BASE_URL}/api/hooks", headers=hf, json=hook, timeout=15
                )
            )["feature"]
            == "webhooks"
        )
        r = httpx.post(f"{API_BASE_URL}/api/hooks", headers=hp, json=hook, timeout=15)
        assert r.status_code == 201, r.text

    def test_05_menu_moderno_so_na_transicao(
        self, empresa_free_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/menus",
            headers=hf,
            json={
                "nome": f"Menu {_RUN}",
                "mensagem_boas_vindas": "Olá! Escolha uma opção.",
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        menu_id = r.json()["id"]
        d = _detail(
            httpx.put(
                f"{API_BASE_URL}/api/v1/menus/{menu_id}",
                headers=hf,
                json={"menu_moderno": True},
                timeout=15,
            )
        )
        assert d["feature"] == "menu_moderno"
        # Salvar sem ligar continua livre.
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/menus/{menu_id}",
            headers=hf,
            json={"nome": "Menu renomeado", "menu_moderno": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_06_white_label_so_ao_mudar_e_grandfathering(
        self, db_url: str, empresa_free_id: int, empresa_ent_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        d = _detail(
            httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
                headers=hf,
                json={"nome_exibicao": "Marca Free", "cor_primaria": "#ff0000"},
                timeout=15,
            )
        )
        assert d["feature"] == "white_label"
        # Sem mexer na marca (só outro campo) passa.
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
            headers=hf,
            json={"nome": f"test-leva-c1-free-{_RUN} renomeada"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Grandfathering (D3): flag `plano.white_label` libera.
        _flag(db_url, empresa_free_id, "white_label", "true")
        _esperar_cache_do_plano()
        try:
            r = httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
                headers=hf,
                json={"nome_exibicao": "Marca Free"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.json()["nome_exibicao"] == "Marca Free"
            # Reenviar o MESMO valor gravado não é "mudar": passa mesmo sem flag.
            _flag(db_url, empresa_free_id, "white_label", None)
            _esperar_cache_do_plano()
            r = httpx.put(
                f"{API_BASE_URL}/api/empresas/{empresa_free_id}",
                headers=hf,
                json={"nome_exibicao": "Marca Free"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
        finally:
            _flag(db_url, empresa_free_id, "white_label", None)
        # Enterprise tem a feature.
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_ent_id}",
            headers=_headers(admin_user_id, empresa_ent_id),
            json={"nome_exibicao": "Marca Ent", "cor_primaria": "#00ff00"},
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_07_waba_so_pro(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        hf = _headers(admin_user_id, empresa_free_id)
        body = {
            "provider": "waba",
            "from_number": f"+5567{_RUN}",
            "default_agent_id": "agente",
        }
        d = _detail(
            httpx.post(
                f"{API_BASE_URL}/api/conexoes", headers=hf, json=body, timeout=15
            )
        )
        assert d["feature"] == "waba"
        d = _detail(
            httpx.post(
                f"{API_BASE_URL}/api/conexoes/waba/finalize",
                headers=hf,
                json={},
                timeout=15,
            )
        )
        assert d["feature"] == "waba"
        # Pro passa o gate de plano (o que vier depois não é 402).
        r = httpx.post(
            f"{API_BASE_URL}/api/conexoes/waba/finalize",
            headers=_headers(admin_user_id, empresa_id),
            json={},
            timeout=15,
        )
        assert r.status_code != 402, r.text

    def test_08_feature_flags_so_superadmin(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        hp = _headers(admin_user_id, empresa_id)  # admin da empresa, NÃO superadmin
        r = httpx.get(f"{API_BASE_URL}/api/v1/feature-flags", headers=hp, timeout=15)
        assert r.status_code == 403, r.text
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/feature-flags/plano.mcp",
            headers=hp,
            json={"key": "plano.mcp", "value": True},
            timeout=15,
        )
        assert r.status_code == 403, r.text
