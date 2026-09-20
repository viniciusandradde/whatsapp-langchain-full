"""Smoke + E2E da leva A da ADR-005 (mig 189): limites que já existiam passam
a valer + limite de agentes + teto de IA do plano no `ia_budget` + uso do plano
nos `/contadores`.

Smoke (sem DB): as rotas existem e exigem service token.
E2E (stack rodando): empresa Pro e empresa Free com o MESMO admin (padrão de
`test_catalogo_modelos_endpoints.py`). No Free cada limite dá 402
`quota_exceeded` legível; a flag `plano.<chave>` (grandfathering, D3) libera
a mesma chamada; o Pro passa. O teto de IA (D4) recusa `limite_usd` acima do
plano com 402 `feature_unavailable` e o GET devolve `teto_plano_usd`.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_a_endpoints.py -m docker_demo -v
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
    @pytest.mark.parametrize(
        ("metodo", "caminho"),
        [
            ("POST", "/api/usuarios"),
            ("POST", "/api/empresas/1/membros"),
            ("POST", "/api/v1/agentes"),
            ("POST", "/api/base-conhecimento"),
            ("POST", "/api/base-conhecimento/upload"),
            ("PUT", "/api/v1/ia-budget"),
            ("GET", "/api/v1/ia-budget"),
            ("GET", "/api/atendimentos/contadores"),
        ],
    )
    def test_rotas_gateadas_exigem_auth(self, metodo: str, caminho: str) -> None:
        resp = _client().request(metodo, caminho)
        assert resp.status_code == 401, (caminho, resp.text)


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


def _criar_empresa(cur, slug_plano: str, nome: str) -> int:
    cur.execute(
        "INSERT INTO empresa (nome, slug, plano, status, plano_id) "
        "VALUES (%s, %s, %s, 'active', (SELECT id FROM plano WHERE slug = %s)) "
        "RETURNING id",
        (nome, nome, slug_plano, slug_plano),
    )
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _dar_perfil_admin(cur, empresa_id: int, user_id: str) -> None:
    cur.execute(
        "INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system) "
        "VALUES (%s, 'Admin', 'Acesso total', TRUE) "
        "ON CONFLICT (empresa_id, nome) DO NOTHING",
        (empresa_id,),
    )
    cur.execute(
        "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
        (empresa_id,),
    )
    row = cur.fetchone()
    assert row is not None
    perfil_id = int(row[0])
    cur.execute(
        "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) "
        "SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING",
        (perfil_id,),
    )
    cur.execute(
        "INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, assigned_by_user_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (user_id, perfil_id, empresa_id, user_id),
    )


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    """Empresa Pro (10 usuários, 5 agentes, 100 docs, teto de IA US$ 100)."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-a-pro-{_RUN}")
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    """User comum (não superadmin) com perfil Admin nas duas empresas."""
    user_id = f"test-leva-a-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Leva A', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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
    """Empresa Free (2 usuários, 1 agente, 5 docs, teto de IA US$ 5)."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "free", f"test-leva-a-free-{_RUN}")
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', FALSE)",
            (eid, admin_user_id),
        )
        _dar_perfil_admin(cur, eid, admin_user_id)
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture()
def usuarios_extras(db_url: str):
    """Dois users soltos (sem membership) para o `/membros` legado."""
    ids = [f"test-leva-a-extra-{_RUN}-{i}" for i in (1, 2)]
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        for uid in ids:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status, is_superadmin)
                VALUES (%s, 'Extra', %s, TRUE, NOW(), NOW(), 'active', FALSE)
                """,
                (uid, f"{uid}@e2e.test"),
            )
    yield ids
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = ANY(%s)', (ids,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


def _flag(db_url: str, empresa_id: int, chave: str, valor_json: str | None) -> None:
    """Cadastra (ou apaga, com None) a exceção `plano.<chave>` direto no banco."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        if valor_json is None:
            cur.execute(
                "DELETE FROM feature_flag WHERE empresa_id = %s AND key = %s",
                (empresa_id, f"plano.{chave}"),
            )
        else:
            cur.execute(
                "INSERT INTO feature_flag (empresa_id, key, value, descricao) "
                "VALUES (%s, %s, %s::jsonb, 'e2e leva A') "
                "ON CONFLICT (empresa_id, key) DO UPDATE SET value = EXCLUDED.value, "
                "ativo = TRUE, updated_at = NOW()",
                (empresa_id, f"plano.{chave}", valor_json),
            )


def _esperar_cache_do_plano() -> None:
    """O snapshot de plano fica 30 s em cache POR PROCESSO da API. Pela tela
    a rota de flags (superadmin) invalida na hora; o teste escreve direto no
    banco, então espera o TTL — uma vez só."""
    import time

    time.sleep(31)


@pytest.mark.docker_demo
class TestE2E:
    def test_01_free_limite_de_agentes_e_grandfathering(
        self, db_url: str, empresa_free_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={"slug": f"ag1-{_RUN}", "nome": "Um", "template_catalog": "agente"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={"slug": f"ag2-{_RUN}", "nome": "Dois", "template_catalog": "agente"},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        d = r.json()["detail"]
        assert d["error"] == "quota_exceeded"
        assert d["recurso"] == "agentes"
        assert (d["quota_used"], d["quota_max"]) == (1, 1)
        assert d["plano_atual"] == "free" and d["upgrade_to"] == "pro"
        assert "agentes de IA" in d["message"]

        # Grandfathering (D3): `plano.limite_agentes = null` = ilimitado.
        _flag(db_url, empresa_free_id, "limite_agentes", "null")
        _esperar_cache_do_plano()
        try:
            r = httpx.post(
                f"{API_BASE_URL}/api/v1/agentes",
                headers=h,
                json={
                    "slug": f"ag2-{_RUN}",
                    "nome": "Dois",
                    "template_catalog": "agente",
                },
                timeout=15,
            )
            assert r.status_code == 201, r.text
        finally:
            _flag(db_url, empresa_free_id, "limite_agentes", None)

    def test_02_pro_cria_varios_agentes(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        for i in range(3):
            r = httpx.post(
                f"{API_BASE_URL}/api/v1/agentes",
                headers=h,
                json={
                    "slug": f"pro{i}-{_RUN}",
                    "nome": f"P{i}",
                    "template_catalog": "agente",
                },
                timeout=15,
            )
            assert r.status_code == 201, r.text

    def test_03_free_limite_de_usuarios_no_membros_legado(
        self, empresa_free_id: int, admin_user_id: str, usuarios_extras: list[str]
    ) -> None:
        # Free = 2 usuários; a empresa já tem 1 (o admin).
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_free_id}/membros",
            headers=h,
            json={"user_id": usuarios_extras[0], "role": "operator"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_free_id}/membros",
            headers=h,
            json={"user_id": usuarios_extras[1], "role": "operator"},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        d = r.json()["detail"]
        assert d["recurso"] == "usuarios" and d["quota_max"] == 2
        # Também no caminho novo `/api/usuarios`.
        r = httpx.post(
            f"{API_BASE_URL}/api/usuarios",
            headers=h,
            json={"nome": "Terceiro", "email": f"terceiro-{_RUN}@e2e.test"},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        assert r.json()["detail"]["recurso"] == "usuarios"

    def test_04_free_limite_de_documentos_kb(
        self, db_url: str, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        # Free = 5 docs. Semeia 5 direto no banco e o 6º pela API é 402.
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            for i in range(5):
                cur.execute(
                    "INSERT INTO documento_conhecimento (empresa_id, titulo, conteudo) "
                    "VALUES (%s, %s, 'x')",
                    (empresa_free_id, f"doc-{i}-{_RUN}"),
                )
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/base-conhecimento",
            headers=h,
            json={"titulo": "sexto", "conteudo": "conteúdo do sexto documento"},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        d = r.json()["detail"]
        assert d["recurso"] == "documentos_kb" and d["quota_max"] == 5
        # upload cai no mesmo gate
        r = httpx.post(
            f"{API_BASE_URL}/api/base-conhecimento/upload",
            headers=h,
            files={"arquivo": ("nota.txt", b"texto", "text/plain")},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        # Pro (100) passa
        h = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/base-conhecimento",
            headers=h,
            json={"titulo": "pro", "conteudo": "conteúdo do documento pro"},
            timeout=15,
        )
        assert r.status_code == 201, r.text

    def test_05_teto_de_ia_do_plano_no_ia_budget(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.get(f"{API_BASE_URL}/api/v1/ia-budget", headers=h, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["teto_plano_usd"] == 5.0  # Free, mesmo sem linha do mês

        r = httpx.put(
            f"{API_BASE_URL}/api/v1/ia-budget",
            headers=h,
            json={"limite_usd": 4.5, "acao_estouro": "alertar", "alerta_pct": 80},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["limite_usd"] == 4.5

        r = httpx.put(
            f"{API_BASE_URL}/api/v1/ia-budget",
            headers=h,
            json={"limite_usd": 6, "acao_estouro": "alertar", "alerta_pct": 80},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        d = r.json()["detail"]
        assert d["error"] == "feature_unavailable"
        assert d["feature"] == "orcamento_ia"
        assert d["teto_plano_usd"] == 5.0 and d["upgrade_to"] == "pro"
        assert "US$ 5.00" in d["message"]

        # O 402 não mexeu no que estava salvo.
        r = httpx.get(f"{API_BASE_URL}/api/v1/ia-budget", headers=h, timeout=15)
        assert r.json()["limite_usd"] == 4.5

        # Pro: teto 100 — 100 passa, 100.01 não.
        h = _headers(admin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/ia-budget",
            headers=h,
            json={"limite_usd": 100, "acao_estouro": "bloquear", "alerta_pct": 90},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/ia-budget",
            headers=h,
            json={"limite_usd": 100.01, "acao_estouro": "bloquear", "alerta_pct": 90},
            timeout=15,
        )
        assert r.status_code == 402, r.text

    def test_06_contadores_trazem_uso_do_plano(
        self, empresa_free_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/contadores", headers=h, timeout=15
        )
        assert r.status_code == 200, r.text
        st = r.json()["plano"]["atendimentos_mes"]
        assert st["limite"] == 100
        assert st["usado"] == 0
        assert st["percentual"] == 0.0
        assert st["atingido"] is False and st["em_alerta"] is False
