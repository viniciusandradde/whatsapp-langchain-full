"""Smoke + E2E da leva E da ADR-005 (mig 193): vigência do plano e
rebaixamento automático — `PUT /api/empresas/{id}/vigencia` (superadmin),
`dias_para_vencer` no plano do painel, avisos D-7/D-3/D0 com claim por etapa
e rebaixamento para Free depois da carência (job do worker rodado aqui
em processo, com notificadores falsos: nada sai pelo WhatsApp).

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_e_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import _criar_empresa, _dar_perfil_admin, _headers

_TZ = "America/Campo_Grande"


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_vigencia_exige_auth(self) -> None:
        resp = _client().put(
            "/api/empresas/1/vigencia", json={"plano_valido_ate": None}
        )
        assert resp.status_code == 401, resp.text


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
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _criar_user(cur, user_id: str, *, superadmin: bool) -> None:
    cur.execute(
        """
        INSERT INTO auth."user" (id, name, email, "emailVerified",
                                  "createdAt", "updatedAt", status, is_superadmin)
        VALUES (%s, 'Test Leva E', %s, TRUE, NOW(), NOW(), 'active', %s)
        """,
        (user_id, f"{user_id}@e2e.test", superadmin),
    )


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-e-pro-{_RUN}")
        cur.execute(
            "UPDATE empresa SET resumo_diario_tz = %s WHERE id = %s", (_TZ, eid)
        )
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-e-user-{_RUN}"
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
    user_id = f"test-leva-e-super-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=True)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _hoje() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date()


def _meio_dia_local() -> datetime:
    """`now_utc` dentro da janela comercial local, no dia de hoje."""
    return (
        datetime.combine(_hoje(), datetime.min.time(), ZoneInfo(_TZ))
        .replace(hour=12)
        .astimezone(UTC)
    )


def _estado(db_url: str, eid: int) -> dict:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT plano, plano_valido_ate, plano_aviso_vencimento_etapa,
                      plano_aviso_vencimento_ref
                 FROM empresa WHERE id = %s""",
            (eid,),
        )
        row = cur.fetchone()
    assert row is not None
    return {"plano": row[0], "valido_ate": row[1], "etapa": row[2], "ref": row[3]}


class _Caixa:
    """Notificador falso: guarda (empresa_id, texto)."""

    def __init__(self) -> None:
        self.cliente: list[tuple[int, str]] = []
        self.plataforma: list[tuple[int, str]] = []

    async def avisar_cliente(self, e, texto: str) -> None:
        self.cliente.append((e.id, texto))

    async def avisar_plataforma(self, e, texto: str) -> None:
        self.plataforma.append((e.id, texto))


@pytest.mark.docker_demo
class TestE2E:
    def test_01_admin_da_empresa_nao_define_vigencia(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/vigencia",
            headers=_headers(admin_user_id, empresa_id),
            json={"plano_valido_ate": (_hoje() + timedelta(days=30)).isoformat()},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_02_superadmin_define_e_o_painel_ve_os_dias(
        self, db_url: str, empresa_id: int, superadmin_user_id: str, admin_user_id: str
    ) -> None:
        alvo = _hoje() + timedelta(days=3)
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/vigencia",
            headers=hs,
            json={"plano_valido_ate": alvo.isoformat()},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["plano_valido_ate"] == alvo.isoformat()
        # A rota limpa o cache do plano: o painel vê na hora, sem esperar 30 s.
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["valido_ate"] == alvo.isoformat()
        assert p["dias_para_vencer"] == 3
        assert p["carencia_dias"] == 5
        # A lista de empresas (o que /companies usa) também traz a data.
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        minha = next(e for e in r.json()["empresas"] if e["id"] == empresa_id)
        assert minha["plano_valido_ate"] == alvo.isoformat()

    async def test_03_aviso_d3_sai_uma_vez_e_respeita_a_janela(
        self, db_url: str, empresa_id: int
    ) -> None:
        from whatsapp_langchain.shared.plano_vigencia import processar_vigencias

        caixa = _Caixa()
        # 03:00 local: fora da janela → nada sai, nada é reivindicado
        madrugada = _meio_dia_local() - timedelta(hours=9)
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            c = await processar_vigencias(
                pool,
                now_utc=madrugada,
                avisar_cliente=caixa.avisar_cliente,
                avisar_plataforma=caixa.avisar_plataforma,
            )
        assert c["avisos"] == 0 and c["fora_da_janela"] >= 1
        assert _estado(db_url, empresa_id)["etapa"] is None

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            c1 = await processar_vigencias(
                pool,
                now_utc=_meio_dia_local(),
                avisar_cliente=caixa.avisar_cliente,
                avisar_plataforma=caixa.avisar_plataforma,
            )
            c2 = await processar_vigencias(
                pool,
                now_utc=_meio_dia_local(),
                avisar_cliente=caixa.avisar_cliente,
                avisar_plataforma=caixa.avisar_plataforma,
            )
        meus_cliente = [t for eid, t in caixa.cliente if eid == empresa_id]
        meus_plat = [t for eid, t in caixa.plataforma if eid == empresa_id]
        assert c1["avisos"] >= 1 and len(meus_cliente) == 1, (c1, caixa.cliente)
        assert "vence em 3 dias" in meus_cliente[0]
        assert "_" not in meus_cliente[0]
        assert len(meus_plat) == 1 and "Plano a vencer" in meus_plat[0]
        # segundo tick no mesmo dia: a etapa já foi reivindicada
        assert not [t for eid, t in caixa.cliente if eid == empresa_id][1:], c2
        st = _estado(db_url, empresa_id)
        assert st["etapa"] == "d3" and st["ref"] == st["valido_ate"]

    async def test_04_renovar_zera_o_aviso_e_vencida_ha_6_dias_rebaixa(
        self, db_url: str, empresa_id: int, superadmin_user_id: str
    ) -> None:
        from whatsapp_langchain.shared.plano_vigencia import processar_vigencias

        # Renovação (leva F fará isso ao registrar o pagamento): data nova → a
        # etapa gravada é de OUTRA data e para de valer.
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/vigencia",
            headers=hs,
            json={"plano_valido_ate": (_hoje() + timedelta(days=60)).isoformat()},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert _estado(db_url, empresa_id)["etapa"] is None

        # Vencida há 6 dias (carência de 5) → rebaixa para Free.
        vencida = _hoje() - timedelta(days=6)
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/vigencia",
            headers=hs,
            json={"plano_valido_ate": vencida.isoformat()},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        caixa = _Caixa()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            c = await processar_vigencias(
                pool,
                now_utc=_meio_dia_local(),
                avisar_cliente=caixa.avisar_cliente,
                avisar_plataforma=caixa.avisar_plataforma,
            )
        assert c["rebaixadas"] >= 1, c
        st = _estado(db_url, empresa_id)
        assert st["plano"] == "free"
        assert st["valido_ate"] is None
        assert st["etapa"] == "rebaixado" and st["ref"] == vencida
        meus = [t for eid, t in caixa.cliente if eid == empresa_id]
        assert len(meus) == 1 and "passou para o plano Free" in meus[0]
        assert any(
            "Plano rebaixado" in t for eid, t in caixa.plataforma if eid == empresa_id
        )
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM audit_log WHERE empresa_id = %s "
                "AND action = 'plano.rebaixado_por_vencimento'",
                (empresa_id,),
            )
            row = cur.fetchone()
        assert row is not None and row[0] == 1
        # Free com data nenhuma: o próximo tick não mexe mais nela.
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            c = await processar_vigencias(
                pool,
                now_utc=_meio_dia_local(),
                avisar_cliente=caixa.avisar_cliente,
                avisar_plataforma=caixa.avisar_plataforma,
            )
        assert len([t for eid, t in caixa.cliente if eid == empresa_id]) == 1

    def test_05_limpar_a_data_e_cortesia(
        self, db_url: str, empresa_id: int, superadmin_user_id: str, admin_user_id: str
    ) -> None:
        hs = _headers(superadmin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/vigencia",
            headers=hs,
            json={"plano_valido_ate": None},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["plano_valido_ate"] is None
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["dias_para_vencer"] is None
