"""E2E do claim serializado por conversa — contra o Postgres de verdade.

Invariante testada: nunca duas rows da mesma `(phone_number, agent_id)` em
`processing` com lease válido ao mesmo tempo, mesmo com N claims concorrentes
(`test_4`), e o claim não deadlocka com o webhook (`test_5`), que toma o mesmo
advisory lock.

⚠️ PARE O WORKER DO DEV ANTES — ele reivindica qualquer row elegível e os
asserts de `attempts`/`status` falham com "outro processo tocou nas rows":

    docker compose -p chatnexus-dev -f docker-compose.yml \\
        -f docker-compose.override.yml stop worker
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
        uv run pytest tests/integration/test_queue_claim_conversa.py -m docker_demo -v -s
    docker compose -p chatnexus-dev -f docker-compose.yml \\
        -f docker-compose.override.yml start worker
"""

from __future__ import annotations

import asyncio
import uuid

import psycopg
import pytest

from whatsapp_langchain.shared.queue import claim_next, enqueue_or_buffer, mark_done

from .helpers import get_db_url

pytestmark = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]
_AGENT = "vsa_tech"
_C1 = f"+5567{_RUN[:4]}10001"  # conversa 1
_C2 = f"+5567{_RUN[:4]}10002"  # conversa 2

_DICA = (
    "outro processo tocou nas rows — o worker do dev está rodando? "
    "Pare com `docker compose -p chatnexus-dev ... stop worker`"
)


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
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active') RETURNING id
            """,
            (f"test-claim-{_RUN}", f"test-claim-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (eid,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def pool(db_url: str):
    """Pool com 8 conexões: `test_4` dispara 8 claims de verdade em paralelo."""
    from psycopg_pool import AsyncConnectionPool

    async def _open():
        p = AsyncConnectionPool(db_url, min_size=1, max_size=8, open=False)
        await p.open(wait=True)
        return p

    loop = asyncio.new_event_loop()
    p = loop.run_until_complete(_open())
    yield loop, p
    loop.run_until_complete(p.close())
    loop.close()


@pytest.fixture(autouse=True)
def _limpa_fila(db_url: str, empresa_id: int):
    """Cada teste termina com a fila da empresa vazia."""
    yield
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))


def _inserir(
    db_url: str,
    empresa_id: int,
    phone: str,
    texto: str,
    *,
    status: str = "queued",
    attempts: int = 0,
    lease: str | None = None,
    atraso_s: int = 0,
) -> int:
    """Row pronta pra claim (`process_after` no passado). `lease` é SQL cru."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO message_queue
                (empresa_id, phone_number, agent_id, thread_id, incoming_message,
                 status, attempts, max_attempts, lease_until,
                 process_after, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 5, {lease or "NULL"},
                    NOW() - interval '1 second',
                    NOW() - interval '10 seconds' + make_interval(secs => %s))
            RETURNING id
            """,
            (
                empresa_id,
                phone,
                _AGENT,
                f"{phone}:{_AGENT}",
                texto,
                status,
                attempts,
                atraso_s,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _estado(db_url: str, ids: list[int]) -> dict[int, tuple[str, int]]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, attempts FROM message_queue WHERE id = ANY(%s)", (ids,)
        )
        return {int(r[0]): (r[1], int(r[2])) for r in cur.fetchall()}


def _conversas_com_duas_processing(db_url: str, empresa_id: int) -> list[tuple]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT phone_number, agent_id, count(*)
              FROM message_queue
             WHERE empresa_id = %s AND status = 'processing' AND lease_until > NOW()
             GROUP BY 1, 2 HAVING count(*) > 1
            """,
            (empresa_id,),
        )
        return cur.fetchall()


class TestClaimPorConversa:
    def test_1_serializa_por_conversa(self, pool, db_url: str, empresa_id: int) -> None:
        """A e B na conversa 1, C na 2: claim → A, C, None; done(A) → B, None."""
        loop, p = pool
        a = _inserir(db_url, empresa_id, _C1, "A", atraso_s=0)
        b = _inserir(db_url, empresa_id, _C1, "B", atraso_s=1)
        c = _inserir(db_url, empresa_id, _C2, "C", atraso_s=2)

        m1 = loop.run_until_complete(claim_next(p, lease_seconds=60))
        m2 = loop.run_until_complete(claim_next(p, lease_seconds=60))
        m3 = loop.run_until_complete(claim_next(p, lease_seconds=60))
        assert m1 is not None and m1.id == a, f"esperava A ({a}), veio {m1 and m1.id}"
        assert m2 is not None and m2.id == c, (
            f"esperava C ({c}) — B ({b}) é da conversa ocupada; veio {m2 and m2.id}"
        )
        assert m3 is None, f"B não podia sair com A em processing; veio {m3.id}"

        loop.run_until_complete(mark_done(p, a, "ok"))
        m4 = loop.run_until_complete(claim_next(p, lease_seconds=60))
        m5 = loop.run_until_complete(claim_next(p, lease_seconds=60))
        assert m4 is not None and m4.id == b, (
            f"após done(A) esperava B; veio {m4 and m4.id}"
        )
        assert m5 is None

        estado = _estado(db_url, [a, b, c])
        assert estado[a] == ("done", 1), _DICA
        assert estado[b] == ("processing", 1), _DICA
        assert estado[c] == ("processing", 1), _DICA

    def test_2_reclaim_respeita_conversa_ocupada(
        self, pool, db_url: str, empresa_id: int
    ) -> None:
        """Row com lease vencido não é reclamada enquanto a conversa tem outra válida."""
        loop, p = pool
        a = _inserir(
            db_url,
            empresa_id,
            _C1,
            "A",
            status="processing",
            attempts=1,
            lease="NOW() - interval '5 seconds'",
        )
        b = _inserir(
            db_url,
            empresa_id,
            _C1,
            "B",
            status="processing",
            attempts=1,
            lease="NOW() + interval '60 seconds'",
            atraso_s=1,
        )

        assert loop.run_until_complete(claim_next(p, lease_seconds=60)) is None
        estado = _estado(db_url, [a, b])
        assert estado[a] == ("processing", 1), _DICA
        assert estado[b] == ("processing", 1), _DICA

    def test_3_lease_null_nao_bloqueia(
        self, pool, db_url: str, empresa_id: int
    ) -> None:
        """`processing` com lease NULL é zumbi sem dono: não prende a conversa."""
        loop, p = pool
        _inserir(
            db_url, empresa_id, _C1, "A", status="processing", attempts=1, lease=None
        )
        b = _inserir(db_url, empresa_id, _C1, "B", atraso_s=1)

        m = loop.run_until_complete(claim_next(p, lease_seconds=60))
        assert m is not None and m.id == b, f"esperava B ({b}); veio {m and m.id}"

    def test_4_oito_claims_concorrentes(
        self, pool, db_url: str, empresa_id: int
    ) -> None:
        """8 claims de verdade em paralelo sobre 4 rows em 2 conversas → 2 saem."""
        loop, p = pool
        ids = [
            _inserir(db_url, empresa_id, _C1, "A1", atraso_s=0),
            _inserir(db_url, empresa_id, _C1, "A2", atraso_s=1),
            _inserir(db_url, empresa_id, _C2, "B1", atraso_s=2),
            _inserir(db_url, empresa_id, _C2, "B2", atraso_s=3),
        ]

        async def _oito():
            return await asyncio.gather(
                *[claim_next(p, lease_seconds=60) for _ in range(8)]
            )

        saidos = [m for m in loop.run_until_complete(_oito()) if m is not None]
        assert len(saidos) == 2, (
            f"esperava 2 claims (1 por conversa), saíram {len(saidos)}"
        )
        assert {m.phone_number for m in saidos} == {_C1, _C2}
        assert {m.id for m in saidos} == {ids[0], ids[2]}, (
            "devia sair o mais antigo de cada"
        )
        assert _conversas_com_duas_processing(db_url, empresa_id) == []

        for m in saidos:
            loop.run_until_complete(mark_done(p, m.id, "ok"))
        restantes = [m for m in loop.run_until_complete(_oito()) if m is not None]
        assert {m.id for m in restantes} == {ids[1], ids[3]}
        assert _conversas_com_duas_processing(db_url, empresa_id) == []

        estado = _estado(db_url, ids)
        assert all(v[1] == 1 for v in estado.values()), _DICA

    def test_5_enqueue_e_claim_sem_deadlock(
        self, pool, db_url: str, empresa_id: int
    ) -> None:
        """Webhook e claim tomam o MESMO advisory lock: nada de DeadlockDetected."""
        loop, p = pool

        async def _misturado():
            tarefas = []
            for i in range(10):
                tarefas.append(
                    enqueue_or_buffer(
                        p,
                        phone_number=_C1,
                        agent_id=_AGENT,
                        body=f"msg {i}",
                        empresa_id=empresa_id,
                        buffer_seconds=0.0,
                        grouping_seconds=0.0,
                    )
                )
                tarefas.append(claim_next(p, lease_seconds=60))
            return await asyncio.gather(*tarefas, return_exceptions=True)

        resultados = loop.run_until_complete(_misturado())
        erros = [r for r in resultados if isinstance(r, BaseException)]
        assert erros == [], f"exceções sob concorrência: {erros}"
        assert _conversas_com_duas_processing(db_url, empresa_id) == []
