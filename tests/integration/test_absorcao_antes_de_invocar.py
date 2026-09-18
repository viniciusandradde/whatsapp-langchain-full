"""E2E de `absorver_pendentes` contra o Postgres do dev.

Cenário: a row A foi reivindicada (`processing`); enquanto a IA não começa,
chegam B e C (texto, `queued`) e D (mídia). Absorver deve levar B e C pro
turno de A — apagando as rows e concatenando no `incoming_message` de A —,
deixar D (mídia é turno próprio) e não tocar em outra conversa.

Pare o worker do dev antes (ele reivindicaria B/C/D):
    docker compose -p chatnexus-dev -f docker-compose.yml -f docker-compose.override.yml stop worker
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
        uv run pytest tests/integration/test_absorcao_antes_de_invocar.py -m docker_demo -v
    docker compose -p chatnexus-dev -f docker-compose.yml -f docker-compose.override.yml start worker
"""

from __future__ import annotations

import asyncio
import uuid

import psycopg
import pytest

from whatsapp_langchain.shared.queue import (
    absorver_pendentes,
    existe_mensagem_mais_nova,
)

from .helpers import get_db_url

pytestmark = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]
_AGENT = "vsa_tech"
_C1 = f"+5567{_RUN[:4]}20001"
_C2 = f"+5567{_RUN[:4]}20002"


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
            "INSERT INTO empresa (nome, slug, plano, status) VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"test-absorcao-{_RUN}", f"test-absorcao-{_RUN}"),
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


def _inserir(
    db_url, empresa_id, phone, texto, *, status="queued", media_uuid=None, atraso_s=0
) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO message_queue
                (empresa_id, phone_number, agent_id, thread_id, incoming_message, status,
                 media_arquivo_uuid, lease_until, process_after, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'processing' THEN NOW() + interval '60 seconds' END,
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
                media_uuid,
                status,
                atraso_s,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _rows(db_url, empresa_id) -> dict[int, tuple[str, str]]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, incoming_message FROM message_queue WHERE empresa_id = %s",
            (empresa_id,),
        )
        return {int(r[0]): (r[1], r[2]) for r in cur.fetchall()}


class TestAbsorcao:
    def test_1_absorve_texto_deixa_midia_e_outra_conversa(
        self, pool, db_url, empresa_id
    ):
        loop, p = pool
        a = _inserir(db_url, empresa_id, _C1, "oi", status="processing")
        b = _inserir(db_url, empresa_id, _C1, "quero saber", atraso_s=1)
        c = _inserir(db_url, empresa_id, _C1, "o preço", atraso_s=2)
        d = _inserir(
            db_url, empresa_id, _C1, "", media_uuid=str(uuid.uuid4()), atraso_s=3
        )
        e = _inserir(db_url, empresa_id, _C2, "outra conversa", atraso_s=1)

        textos = loop.run_until_complete(
            absorver_pendentes(p, phone_number=_C1, agent_id=_AGENT, message_id=a)
        )

        assert textos == ["quero saber", "o preço"]
        rows = _rows(db_url, empresa_id)
        assert b not in rows and c not in rows, "rows absorvidas são apagadas"
        assert rows[a] == ("processing", "oi\nquero saber\no preço")
        assert rows[d][0] == "queued", "mídia é turno próprio"
        assert rows[e] == ("queued", "outra conversa")

        # D continua mais nova que A → a resposta de A ainda será engolida por D.
        assert loop.run_until_complete(
            existe_mensagem_mais_nova(
                p, phone_number=_C1, agent_id=_AGENT, message_id=a
            )
        )

    def test_2_sem_pendente_nao_muda_nada(self, pool, db_url, empresa_id):
        loop, p = pool
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,)
            )
        a = _inserir(db_url, empresa_id, _C1, "oi", status="processing")

        assert (
            loop.run_until_complete(
                absorver_pendentes(p, phone_number=_C1, agent_id=_AGENT, message_id=a)
            )
            == []
        )
        assert _rows(db_url, empresa_id)[a] == ("processing", "oi")
        assert not loop.run_until_complete(
            existe_mensagem_mais_nova(
                p, phone_number=_C1, agent_id=_AGENT, message_id=a
            )
        )

    def test_3_nao_absorve_row_anterior_nem_ja_reivindicada(
        self, pool, db_url, empresa_id
    ):
        """Só `id >` e `queued`: retry antigo e row de outro slot ficam onde estão."""
        loop, p = pool
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,)
            )
        antiga = _inserir(db_url, empresa_id, _C1, "antiga")
        a = _inserir(db_url, empresa_id, _C1, "oi", status="processing", atraso_s=1)
        outra_processing = _inserir(
            db_url, empresa_id, _C1, "de outro slot", status="processing", atraso_s=2
        )

        assert (
            loop.run_until_complete(
                absorver_pendentes(p, phone_number=_C1, agent_id=_AGENT, message_id=a)
            )
            == []
        )
        rows = _rows(db_url, empresa_id)
        assert set(rows) == {antiga, a, outra_processing}
