"""E2E da justiça entre empresas no claim — contra o Postgres do dev.

Hospital (empresa H) manda 5 conversas num burst; a PME (empresa P) manda UMA
mensagem 1 s depois. Sem justiça, a PME esperaria as 5 do hospital. Com a
ordenação por posição na fila da própria empresa, a PME sai em 2º lugar.

Pare o worker do dev antes (ver test_queue_claim_conversa.py).
"""

from __future__ import annotations

import asyncio
import uuid

import psycopg
import pytest

from whatsapp_langchain.shared.queue import claim_next

from .helpers import get_db_url

pytestmark = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]
_AGENT = "vsa_tech"


@pytest.fixture(scope="module")
def db_url() -> str:
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresas(db_url: str):
    ids = []
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        for nome in ("hospital", "pme", "clinica"):
            cur.execute(
                "INSERT INTO empresa (nome, slug, plano, status) VALUES (%s, %s, 'free', 'active') RETURNING id",
                (f"test-justica-{nome}-{_RUN}", f"test-justica-{nome}-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            ids.append(int(row[0]))
    yield tuple(ids)
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM message_queue WHERE empresa_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM empresa WHERE id = ANY(%s)", (ids,))


@pytest.fixture(scope="module")
def pool(db_url: str):
    from psycopg_pool import AsyncConnectionPool

    async def _open():
        p = AsyncConnectionPool(db_url, min_size=1, max_size=3, open=False)
        await p.open(wait=True)
        return p

    loop = asyncio.new_event_loop()
    p = loop.run_until_complete(_open())
    yield loop, p
    loop.run_until_complete(p.close())
    loop.close()


@pytest.fixture(autouse=True)
def _limpa(db_url, empresas):
    yield
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM message_queue WHERE empresa_id = ANY(%s)", (list(empresas),)
        )


def _inserir(db_url, empresa_id, phone, texto, *, atraso_s) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO message_queue
                (empresa_id, phone_number, agent_id, thread_id, incoming_message,
                 process_after, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW() - interval '1 second',
                    NOW() - interval '60 seconds' + make_interval(secs => %s))
            RETURNING id
            """,
            (empresa_id, phone, _AGENT, f"{phone}:{_AGENT}", texto, atraso_s),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _claims(loop, p, n):
    return [loop.run_until_complete(claim_next(p, lease_seconds=60)) for _ in range(n)]


class TestJustica:
    def test_1_pme_sai_em_segundo_apesar_de_chegar_depois(self, pool, db_url, empresas):
        loop, p = pool
        hospital, pme, _ = empresas
        h = [
            _inserir(db_url, hospital, f"+5567{_RUN[:4]}3000{i}", f"h{i}", atraso_s=i)
            for i in range(5)
        ]
        pm = _inserir(db_url, pme, f"+5567{_RUN[:4]}31000", "pme", atraso_s=10)

        saidos = [m.id for m in _claims(loop, p, 6) if m is not None]
        assert saidos == [h[0], pm, h[1], h[2], h[3], h[4]], saidos

    def test_2_tres_empresas_intercalam(self, pool, db_url, empresas):
        loop, p = pool
        hospital, pme, clinica = empresas
        h = [
            _inserir(db_url, hospital, f"+5567{_RUN[:4]}3200{i}", f"h{i}", atraso_s=i)
            for i in range(3)
        ]
        c = [
            _inserir(
                db_url, clinica, f"+5567{_RUN[:4]}3300{i}", f"c{i}", atraso_s=10 + i
            )
            for i in range(2)
        ]
        pm = _inserir(db_url, pme, f"+5567{_RUN[:4]}34000", "pme", atraso_s=20)

        saidos = [m.id for m in _claims(loop, p, 6) if m is not None]
        # posição 1 de cada empresa por idade, depois posição 2, depois posição 3
        assert saidos == [h[0], c[0], pm, h[1], c[1], h[2]], saidos

    def test_3_mesma_conversa_continua_em_ordem(self, pool, db_url, empresas):
        """A justiça é entre empresas; dentro da conversa a ordem é a de chegada."""
        loop, p = pool
        hospital, pme, _ = empresas
        phone = f"+5567{_RUN[:4]}35000"
        a = _inserir(db_url, hospital, phone, "a", atraso_s=0)
        _inserir(db_url, hospital, phone, "b", atraso_s=1)
        pm = _inserir(db_url, pme, f"+5567{_RUN[:4]}36000", "pme", atraso_s=2)

        saidos = [m.id if m else None for m in _claims(loop, p, 3)]
        # b não sai enquanto a está em processing (uma por conversa)
        assert saidos == [a, pm, None], saidos
