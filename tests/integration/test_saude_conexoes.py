"""Smoke + E2E da saúde das conexões (mig 196): silêncio contra baseline,
sonda ativa com anti-flap, episódios em `conexao_alerta`, aviso agrupado ao
canal (notificador falso — nada sai pelo Telegram/WhatsApp), rotas
`/api/monitor/*` e o `connection.update` do webhook da Evolution.

O job do worker (`avaliar_saude`) roda AQUI, em processo, com a sonda e o
notificador injetados e `now_utc` fixado numa terça-feira às 14 h locais —
a baseline semeada é de dias úteis 08–17 h, 4 mensagens por hora.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_saude_conexoes.py -m docker_demo -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import _criar_empresa, _dar_perfil_admin, _headers
from .test_plano_leva_e_endpoints import _apagar_empresa, _criar_user

_TZ = "America/Campo_Grande"
_RUN = uuid.uuid4().hex[:8]


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_monitor_conexoes_exige_auth(self) -> None:
        assert _client().get("/api/monitor/conexoes").status_code == 401

    def test_monitor_banner_exige_auth(self) -> None:
        assert _client().get("/api/monitor/banner").status_code == 401


# --- fixtures ----------------------------------------------------------------


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
            cur.execute("SELECT 1 FROM saude_conexoes_estado")
    except Exception:
        pytest.skip("DB não acessível ou mig 196 ausente. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-saude-{_RUN}")
        cur.execute("UPDATE empresa SET timezone = %s WHERE id = %s", (_TZ, eid))
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def instance_name() -> str:
    return f"saude-{_RUN}"


@pytest.fixture(scope="module")
def conexao_id(db_url: str, empresa_id: int, instance_name: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conexao (empresa_id, provider, from_number, display_name, status,
                                 connection_state, payload_json)
            VALUES (%s, 'evolution', %s, 'Comercial', 'active', 'open', %s::jsonb)
            RETURNING id
            """,
            (empresa_id, f"+5567{_RUN[:8]}", f'{{"instance_name": "{instance_name}"}}'),
        )
        cid = cur.fetchone()[0]
    yield cid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM message_queue WHERE conexao_id = %s", (cid,))
        cur.execute("DELETE FROM conexao WHERE id = %s", (cid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-saude-user-{_RUN}"
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
    user_id = f"test-saude-super-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        _criar_user(cur, user_id, superadmin=True)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


# --- tempo e semeadura ------------------------------------------------------


def _ultima_terca_14h() -> datetime:
    """A terça-feira mais recente, 14:00 em Campo Grande, em UTC — com pelo
    menos 1 h de folga em relação a agora (para a marca d'água não passar
    do presente)."""
    agora_local = datetime.now(UTC).astimezone(ZoneInfo(_TZ))
    dia = agora_local.date()
    while (
        dia.isoweekday() != 2
        or datetime.combine(dia, datetime.min.time(), ZoneInfo(_TZ)).replace(hour=15)
        > agora_local
    ):
        dia -= timedelta(days=1)
    return (
        datetime.combine(dia, datetime.min.time(), ZoneInfo(_TZ))
        .replace(hour=14)
        .astimezone(UTC)
    )


def _semear_historico(
    db_url: str, empresa_id: int, conexao_id: int, ate_utc: datetime
) -> datetime:
    """21 dias úteis de 08–17 h locais, 4 mensagens por hora, terminando na
    terça às 08:00 (a última recebida). Devolve o carimbo da última."""
    zona = ZoneInfo(_TZ)
    fim_local = ate_utc.astimezone(zona)
    rows = []
    ultima = None
    for d in range(21, -1, -1):
        dia = (fim_local - timedelta(days=d)).date()
        if dia.isoweekday() > 5:
            continue
        for hora in range(8, 18):
            for k in range(4):
                t = datetime.combine(dia, datetime.min.time(), zona).replace(
                    hour=hora, minute=k * 15
                )
                if t > fim_local.replace(hour=8, minute=0, second=0, microsecond=0):
                    continue
                t_utc = t.astimezone(UTC)
                ultima = t_utc if ultima is None or t_utc > ultima else ultima
                rows.append(
                    (
                        f"e2e-saude:{_RUN}:{len(rows)}",
                        f"+5567{_RUN[:8]}",
                        "vsa_tech",
                        f"+5567{_RUN[:8]}:vsa_tech",
                        f"mensagem {len(rows)}",
                        "done",
                        t_utc,
                        empresa_id,
                        conexao_id,
                    )
                )
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO message_queue (message_id, phone_number, agent_id, thread_id,
                                       incoming_message, status, created_at,
                                       empresa_id, conexao_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        # a marca d'água volta para antes do histórico: o tick acumula tudo
        cur.execute(
            "UPDATE saude_conexoes_estado SET marca_atividade = %s WHERE id = 1",
            (ate_utc - timedelta(days=30),),
        )
    assert ultima is not None
    return ultima


def _conexao_estado(db_url: str, cid: int) -> dict:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT connection_state, state_message, desconexao_codigo, desconexao_em,
                      sonda_falhas_seguidas, ultimo_health_check_ok, ultimo_inbound_em
                 FROM conexao WHERE id = %s""",
            (cid,),
        )
        r = cur.fetchone()
    assert r is not None
    return {
        "state": r[0],
        "msg": r[1],
        "codigo": r[2],
        "desde": r[3],
        "falhas": r[4],
        "hc_ok": r[5],
        "ultimo_inbound": r[6],
    }


def _alertas(db_url: str, cid: int) -> list[dict]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tipo, detalhe, notificado_em, resolvido_em, id FROM conexao_alerta "
            "WHERE conexao_id = %s ORDER BY id",
            (cid,),
        )
        return [
            {
                "tipo": r[0],
                "detalhe": r[1],
                "notificado": r[2],
                "resolvido": r[3],
                "id": r[4],
            }
            for r in cur.fetchall()
        ]


class _Caixa:
    def __init__(self) -> None:
        self.msgs: list[tuple[str, list[str]]] = []

    async def notificar(self, titulo: str, linhas: list[str]) -> bool:
        self.msgs.append((titulo, linhas))
        return True


def _sonda(ok: bool, motivo: str, *, so_conexao: int):
    """Sonda falsa SÓ para a conexão do teste: o job varre todas as conexões
    ativas do banco, e as outras não podem ganhar falhas/alertas de mentira."""
    from whatsapp_langchain.shared.saude_conexoes import ResultadoSonda

    async def _f(c):
        if c.id != so_conexao:
            return None
        return ResultadoSonda(
            ok=ok,
            estado="open",
            responde=ok,
            latencia_ms=90 if ok else None,
            motivo=motivo,
        )

    return _f


async def _sem_sonda(_c):
    return None


async def _tick(db_url: str, *, now_utc: datetime, sondar, caixa: _Caixa) -> dict:
    from whatsapp_langchain.shared.saude_conexoes import avaliar_saude

    async with AsyncConnectionPool(db_url, min_size=1, max_size=4) as pool:
        return await avaliar_saude(
            pool, now_utc=now_utc, sondar=sondar, notificar=caixa.notificar, forcar=True
        )


def _evolution_apikey() -> str | None:
    if os.environ.get("EVOLUTION_API_KEY"):
        return os.environ["EVOLUTION_API_KEY"]
    env = Path(__file__).resolve().parents[2] / ".env.local"
    if env.exists():
        for linha in env.read_text().splitlines():
            if linha.startswith("EVOLUTION_API_KEY="):
                return linha.split("=", 1)[1].strip().strip('"')
    return None


# --- E2E ----------------------------------------------------------------------


@pytest.mark.docker_demo
class TestE2E:
    async def test_01_silencio_contra_baseline_abre_e_avisa_uma_vez(
        self, db_url: str, empresa_id: int, conexao_id: int
    ) -> None:
        terca_14h = _ultima_terca_14h()
        ultima = _semear_historico(db_url, empresa_id, conexao_id, terca_14h)
        caixa = _Caixa()
        c = await _tick(
            db_url,
            now_utc=terca_14h,
            sondar=_sonda(True, "conexão responde", so_conexao=conexao_id),
            caixa=caixa,
        )
        assert c["erros"] == 0 and c["conexoes"] >= 1, c

        est = _conexao_estado(db_url, conexao_id)
        assert est["ultimo_inbound"] == ultima
        assert est["hc_ok"] is True and est["falhas"] == 0

        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), sum(recebidas) FROM conexao_atividade WHERE conexao_id = %s",
                (conexao_id,),
            )
            n, total = cur.fetchone()
        assert n >= 100 and total >= 400, (n, total)

        meus = [a for a in _alertas(db_url, conexao_id)]
        assert [a["tipo"] for a in meus] == ["sem_atividade"], meus
        assert meus[0]["detalhe"]["esperadas"] >= 8  # 6 h × 4/h = 24
        assert meus[0]["detalhe"]["sonda_ok"] is True
        assert meus[0]["notificado"] is not None

        abertas = [m for m in caixa.msgs if m[0].startswith("🔴")]
        assert len(abertas) == 1, caixa.msgs
        linha = next(li for li in abertas[0][1] if f"({empresa_id})" in li)
        assert "sem mensagens há 6 h" in linha and "esperadas ≈ 24" in linha
        assert "conexão responde" in linha
        assert "_" not in linha

        # segundo tick, mesmo instante: episódio já ativo — nenhuma mensagem nova
        caixa2 = _Caixa()
        await _tick(
            db_url,
            now_utc=terca_14h,
            sondar=_sonda(True, "conexão responde", so_conexao=conexao_id),
            caixa=caixa2,
        )
        assert not [
            m for m in caixa2.msgs if any(f"({empresa_id})" in li for li in m[1])
        ], caixa2.msgs

    async def test_02_duas_sondas_ruins_abrem_conexao_caida(
        self, db_url: str, empresa_id: int, conexao_id: int
    ) -> None:
        terca_14h = _ultima_terca_14h()
        ruim = _sonda(False, "sem resposta do WhatsApp em 8 s", so_conexao=conexao_id)
        caixa = _Caixa()
        await _tick(
            db_url, now_utc=terca_14h + timedelta(minutes=5), sondar=ruim, caixa=caixa
        )
        est = _conexao_estado(db_url, conexao_id)
        assert est["falhas"] == 1 and est["hc_ok"] is False
        assert [
            a["tipo"] for a in _alertas(db_url, conexao_id) if a["resolvido"] is None
        ] == ["sem_atividade"]
        assert not [
            m for m in caixa.msgs if any(f"({empresa_id})" in li for li in m[1])
        ]

        await _tick(
            db_url, now_utc=terca_14h + timedelta(minutes=10), sondar=ruim, caixa=caixa
        )
        est = _conexao_estado(db_url, conexao_id)
        assert est["falhas"] == 2 and est["desde"] is not None
        ativos = {
            a["tipo"]: a for a in _alertas(db_url, conexao_id) if a["resolvido"] is None
        }
        assert set(ativos) == {"sem_atividade", "conexao_caida"}, ativos
        assert ativos["conexao_caida"]["detalhe"]["origem"] == "sonda"
        abertas = [m for m in caixa.msgs if m[0].startswith("🔴")]
        assert len(abertas) == 1
        linha = next(li for li in abertas[0][1] if f"({empresa_id})" in li)
        assert "sem resposta do WhatsApp em 8 s" in linha

    async def test_03_sonda_boa_resolve_a_queda_sem_aviso_curto(
        self, db_url: str, empresa_id: int, conexao_id: int
    ) -> None:
        terca_14h = _ultima_terca_14h()
        caixa = _Caixa()
        await _tick(
            db_url,
            now_utc=terca_14h + timedelta(minutes=15),
            sondar=_sonda(True, "conexão responde", so_conexao=conexao_id),
            caixa=caixa,
        )
        est = _conexao_estado(db_url, conexao_id)
        assert est["falhas"] == 0 and est["hc_ok"] is True and est["desde"] is None
        ativos = [
            a["tipo"] for a in _alertas(db_url, conexao_id) if a["resolvido"] is None
        ]
        assert ativos == ["sem_atividade"]
        # viveu menos de 30 min: resolve em silêncio (anti-ruído)
        assert not [m for m in caixa.msgs if m[0].startswith("✅")], caixa.msgs

    def test_04_rotas_do_painel(
        self,
        db_url: str,
        empresa_id: int,
        conexao_id: int,
        admin_user_id: str,
        superadmin_user_id: str,
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/monitor/conexoes",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 403, r.text

        r = httpx.get(
            f"{API_BASE_URL}/api/monitor/conexoes",
            headers=_headers(superadmin_user_id, empresa_id),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert "estado" in corpo and "items" in corpo
        item = next(i for i in corpo["items"] if i["conexao_id"] == conexao_id)
        assert item["empresa_id"] == empresa_id
        assert item["monitorada"] is True
        assert item["ultimo_inbound_em"] is not None
        assert item["esperadas_24h"] > 0
        assert [a["tipo"] for a in item["alertas"]] == ["sem_atividade"]
        # com alerta vem antes de quem não tem
        assert corpo["items"][0]["alertas"], corpo["items"][0]

        r = httpx.get(
            f"{API_BASE_URL}/api/monitor/banner",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["caidas"] == []

    async def test_05_connection_update_do_webhook_abre_na_hora(
        self,
        db_url: str,
        empresa_id: int,
        conexao_id: int,
        instance_name: str,
        admin_user_id: str,
    ) -> None:
        apikey = _evolution_apikey()
        if not apikey:
            pytest.skip("EVOLUTION_API_KEY do dev não encontrada (env ou .env.local)")

        def _webhook(
            state: str, status_reason: int, event: str = "connection.update"
        ) -> None:
            r = httpx.post(
                f"{API_BASE_URL}/webhook/evolution",
                headers={"apikey": apikey},
                json={
                    "event": event,
                    "instance": instance_name,
                    "data": {
                        "instance": instance_name,
                        "state": state,
                        "statusReason": status_reason,
                        "wuid": f"5567{_RUN[:8]}@s.whatsapp.net",
                    },
                },
                timeout=15,
            )
            assert r.status_code == 200, r.text

        def _caida_ativa() -> dict | None:
            return next(
                (
                    a
                    for a in _alertas(db_url, conexao_id)
                    if a["tipo"] == "conexao_caida" and a["resolvido"] is None
                ),
                None,
            )

        # (a) o aparelho foi desvinculado: estado passivo gravado na hora
        _webhook("close", 401)
        est = _conexao_estado(db_url, conexao_id)
        assert est["state"] == "disconnected"
        assert est["codigo"] == 401
        assert est["msg"] == "aparelho desvinculado no celular"
        assert est["desde"] is not None

        # (b) o tick abre na hora (sem esperar sonda), mas dentro do cooldown
        # de 6 h reativa o MESMO episódio do teste 03 — e não avisa de novo
        antigo = next(
            a for a in _alertas(db_url, conexao_id) if a["tipo"] == "conexao_caida"
        )
        caixa = _Caixa()
        t0 = _ultima_terca_14h() + timedelta(minutes=20)
        await _tick(db_url, now_utc=t0, sondar=_sem_sonda, caixa=caixa)
        ativo = _caida_ativa()
        assert ativo is not None and ativo["id"] == antigo["id"], ativo
        assert ativo["detalhe"]["origem"] == "evento"
        assert ativo["detalhe"]["motivo"] == "aparelho desvinculado no celular"
        assert not [m for m in caixa.msgs if m[0].startswith("🔴")], caixa.msgs

        r = httpx.get(
            f"{API_BASE_URL}/api/monitor/banner",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        caidas = r.json()["caidas"]
        assert len(caidas) == 1 and caidas[0]["conexao_id"] == conexao_id
        assert caidas[0]["motivo"] == "aparelho desvinculado no celular"

        # (c) o aparelho voltou (evento em caixa alta): `open` limpa motivo e
        # carimbo; o tick resolve em silêncio (viveu menos de 30 min)
        _webhook("open", 200, event="CONNECTION_UPDATE")
        est = _conexao_estado(db_url, conexao_id)
        assert est["state"] == "open" and est["codigo"] is None and est["desde"] is None
        await _tick(
            db_url, now_utc=t0 + timedelta(minutes=5), sondar=_sem_sonda, caixa=caixa
        )
        assert _caida_ativa() is None
        assert not [m for m in caixa.msgs if m[0].startswith("✅")], caixa.msgs

        # (d) fora do cooldown, o mesmo LOGOUT vira episódio NOVO e avisa o canal
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE conexao_alerta SET resolvido_em = NOW() - interval '7 hours' "
                "WHERE conexao_id = %s AND tipo = 'conexao_caida'",
                (conexao_id,),
            )
        _webhook("close", 401)
        caixa = _Caixa()
        await _tick(
            db_url, now_utc=t0 + timedelta(minutes=10), sondar=_sem_sonda, caixa=caixa
        )
        ativo = _caida_ativa()
        assert ativo is not None and ativo["id"] != antigo["id"], ativo
        assert ativo["notificado"] is not None
        abertas = [m for m in caixa.msgs if m[0].startswith("🔴")]
        assert len(abertas) == 1, caixa.msgs
        linha = next(li for li in abertas[0][1] if f"({empresa_id})" in li)
        assert "aparelho desvinculado no celular — desde" in linha
        assert "_" not in linha

        # (e) volta de novo → resolve; o `sem_atividade` segue (nada chegou)
        _webhook("open", 200)
        await _tick(
            db_url, now_utc=t0 + timedelta(minutes=15), sondar=_sem_sonda, caixa=caixa
        )
        ativos = [
            a["tipo"] for a in _alertas(db_url, conexao_id) if a["resolvido"] is None
        ]
        assert ativos == ["sem_atividade"], ativos
