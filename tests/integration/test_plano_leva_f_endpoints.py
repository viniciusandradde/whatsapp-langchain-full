"""Smoke + E2E da leva F da ADR-005 (mig 194): cobrança por planos hospedados
— links dos planos (superadmin), registro manual de pagamento
(`POST /api/empresas/{id}/pagamentos`) que grava em `transacao` e estende
a vigência (leva E), histórico com período.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_f_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import _criar_empresa, _dar_perfil_admin, _headers
from .test_plano_leva_e_endpoints import _criar_user, _hoje


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    @pytest.mark.parametrize(
        ("metodo", "caminho"),
        [
            ("POST", "/api/empresas/1/pagamentos"),
            ("GET", "/api/empresas/1/pagamentos"),
            ("PUT", "/api/billing/planos/pro/links"),
        ],
    )
    def test_rotas_exigem_auth(self, metodo: str, caminho: str) -> None:
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
        cur.execute("DELETE FROM audit_log WHERE empresa_id = %s", (eid,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))  # transacao é CASCADE


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    """Nasce Free: o pagamento é o que a sobe para Pro."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "free", f"test-leva-f-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-f-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=False)
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
def superadmin_user_id(db_url: str):
    user_id = f"test-leva-f-super-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=True)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def links_originais(db_url: str):
    """Guarda e devolve os links do plano Pro (é dado global do catálogo)."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT link_infinitepay, link_mercadopago FROM plano WHERE slug = 'pro'"
        )
        row = cur.fetchone()
    yield row
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE plano SET link_infinitepay = %s, link_mercadopago = %s WHERE slug = 'pro'",
            (row[0] if row else None, row[1] if row else None),
        )


def _pagamento(**kw) -> dict:
    inicio = _hoje()
    base = {
        "plano_slug": "pro",
        "gateway": "infinitepay",
        "gateway_id": f"ip-{_RUN}-1",
        "valor_brl": 299.0,
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": (inicio + timedelta(days=29)).isoformat(),
        "observacao": "Pix conciliado no app",
    }
    base.update(kw)
    return base


@pytest.mark.docker_demo
class TestE2E:
    def test_01_admin_da_empresa_nao_registra_pagamento_nem_edita_links(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=h,
            json=_pagamento(),
            timeout=15,
        )
        assert r.status_code == 403, r.text
        r = httpx.put(
            f"{API_BASE_URL}/api/billing/planos/pro/links",
            headers=h,
            json={"link_infinitepay": "https://pay.infinitepay.io/x"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_02_superadmin_cola_os_links_e_o_catalogo_mostra(
        self,
        empresa_id: int,
        superadmin_user_id: str,
        admin_user_id: str,
        links_originais,
    ) -> None:
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/billing/planos/pro/links",
            headers=hs,
            json={"link_infinitepay": "http://pay.infinitepay.io/x"},  # sem https
            timeout=15,
        )
        assert r.status_code == 400, r.text
        r = httpx.put(
            f"{API_BASE_URL}/api/billing/planos/pro/links",
            headers=hs,
            json={
                "link_infinitepay": f"https://pay.infinitepay.io/vsa/pro-{_RUN}",
                "link_mercadopago": f"https://www.mercadopago.com.br/subscriptions/checkout?preapproval_plan_id={_RUN}",
            },
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # O catálogo (o que o /billing do cliente lê) traz os links.
        r = httpx.get(
            f"{API_BASE_URL}/api/billing/planos",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        pro = next(p for p in r.json()["items"] if p["slug"] == "pro")
        assert pro["link_infinitepay"].endswith(f"pro-{_RUN}")
        assert _RUN in pro["link_mercadopago"]

    def test_03_registrar_pagamento_sobe_o_plano_e_estende_a_vigencia(
        self, db_url: str, empresa_id: int, superadmin_user_id: str, admin_user_id: str
    ) -> None:
        hs = _headers(superadmin_user_id, empresa_id)
        corpo = _pagamento()
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            json=corpo,
            timeout=20,
        )
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["plano"] == "pro" and d["plano_anterior"] == "free"
        assert d["plano_valido_ate"] == corpo["periodo_fim"]
        assert d["whatsapp_enviado"] is False  # empresa sem telefone do resumo diário
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT plano, plano_valido_ate, plano_aviso_vencimento_etapa FROM empresa WHERE id = %s",
                (empresa_id,),
            )
            emp = cur.fetchone()
            cur.execute(
                "SELECT tipo, status, gateway, gateway_id, valor_brl, periodo_inicio, periodo_fim "
                "FROM transacao WHERE id = %s",
                (d["transacao_id"],),
            )
            tx = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM audit_log WHERE empresa_id = %s "
                "AND action = 'plano.pagamento_registrado'",
                (empresa_id,),
            )
            aud = cur.fetchone()
        assert emp is not None and emp[0] == "pro"
        assert emp[1] == date.fromisoformat(corpo["periodo_fim"]) and emp[2] is None
        assert tx is not None and tx[:4] == (
            "assinatura",
            "pago",
            "infinitepay",
            corpo["gateway_id"],
        )
        assert float(tx[4]) == 299.0
        assert tx[5] == date.fromisoformat(corpo["periodo_inicio"])
        assert aud is not None and aud[0] == 1
        # O plano do painel (leva D/E) vê o Pro e a data na hora.
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == "pro"
        assert r.json()["valido_ate"] == corpo["periodo_fim"]

    def test_04_duplicado_da_409_e_historico_sugere_o_proximo_periodo(
        self, empresa_id: int, superadmin_user_id: str, admin_user_id: str
    ) -> None:
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            json=_pagamento(),  # mesmo gateway_id
            timeout=20,
        )
        assert r.status_code == 409, r.text
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            json=_pagamento(
                gateway_id=None,
                periodo_inicio=_hoje().isoformat(),
                periodo_fim=(_hoje() - timedelta(days=1)).isoformat(),
            ),
            timeout=20,
        )
        assert r.status_code == 400, r.text
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            json=_pagamento(plano_slug="free", gateway="manual", gateway_id=None),
            timeout=20,
        )
        assert r.status_code == 400, r.text
        # Histórico (membro lê) com período; sugestão emenda no fim da vigência.
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["plano_atual"] == "pro"
        assert (
            len(d["items"]) == 1
            and d["items"][0]["periodo_fim"] == d["plano_valido_ate"]
        )
        fim = date.fromisoformat(d["plano_valido_ate"])
        assert d["sugestao"]["periodo_inicio"] == (fim + timedelta(days=1)).isoformat()
        # /billing/historico (cliente) também traz o período.
        r = httpx.get(
            f"{API_BASE_URL}/api/billing/historico",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["items"][0]["periodo_inicio"] is not None

    def test_05_renovacao_manual_emenda_e_zera_o_aviso(
        self, db_url: str, empresa_id: int, superadmin_user_id: str
    ) -> None:
        # Simula um aviso já enviado para a data atual: a renovação zera.
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE empresa SET plano_aviso_vencimento_etapa = 'd7', "
                "plano_aviso_vencimento_ref = plano_valido_ate WHERE id = %s",
                (empresa_id,),
            )
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            timeout=15,
        )
        sug = r.json()["sugestao"]
        r = httpx.post(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/pagamentos",
            headers=hs,
            json=_pagamento(
                gateway="manual",
                gateway_id=None,
                periodo_inicio=sug["periodo_inicio"],
                periodo_fim=sug["periodo_fim"],
                observacao="Transferência",
            ),
            timeout=20,
        )
        assert r.status_code == 201, r.text
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT plano_valido_ate, plano_aviso_vencimento_etapa FROM empresa WHERE id = %s",
                (empresa_id,),
            )
            emp = cur.fetchone()
        assert emp is not None
        assert emp[0] == date.fromisoformat(sug["periodo_fim"]) and emp[1] is None
