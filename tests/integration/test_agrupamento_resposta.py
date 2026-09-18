"""Smoke + E2E do agrupamento adaptativo de resposta (mig 144).

O agente respondia a cada fragmento que o cliente mandava. Estes testes
travam o contrato oposto: a PRIMEIRA mensagem de um turno continua respondida
na hora, e as seguintes agrupam numa resposta só.

Smoke (sem DB): valida que o PATCH da conexão exige service token.
E2E (com stack rodando): enfileira em sequência e confere que virou uma row,
que o teto é respeitado e que o kill switch (0) volta ao comportamento antigo.

Para rodar só smoke:
    uv run pytest tests/integration/test_agrupamento_resposta.py::TestSmoke -v

Para rodar E2E (precisa make up + make migrate):
    uv run pytest tests/integration/test_agrupamento_resposta.py::TestE2E -v -s
"""

from __future__ import annotations

import asyncio
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
    """Rota registrada e protegida."""

    def test_patch_conexao_sem_auth_401(self) -> None:
        resp = _client().patch(
            "/api/conexoes/1", json={"resposta_agrupamento_segundos": 8}
        )
        assert resp.status_code == 401

    def test_get_conexoes_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes").status_code == 401


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================


pytestmark_e2e = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]
_PHONE = f"+5567{_RUN[:4]}00000"
_AGENT = "vsa_tech"


@pytest.fixture(scope="module")
def db_url() -> str:
    """Skip se a stack não está rodando."""
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


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active') RETURNING id
            """,
            (f"test-agrup-{_RUN}", f"test-agrup-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def conexao_id(db_url: str, empresa_id: int) -> int:
    """Conexão da empresa de teste — nasce com o default de 8s (mig 144)."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conexao (empresa_id, provider, from_number,
                                 display_name, default_agent_id, status)
            VALUES (%s, 'evolution', %s, %s, %s, 'active')
            RETURNING id
            """,
            (empresa_id, f"+5567{_RUN[:4]}11111", f"conn-{_RUN}", _AGENT),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


async def _enqueue(pool, **kwargs):
    from whatsapp_langchain.shared.queue import enqueue_or_buffer

    return await enqueue_or_buffer(pool, **kwargs)


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


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo real contra Postgres."""

    # autouse DENTRO da classe: no nível do módulo ele arrastaria `db_url` pro
    # TestSmoke e faria o smoke pular fora da stack — justo o que precisa rodar
    # em CI.
    @pytest.fixture(autouse=True)
    def _limpa_fila(self, db_url: str, empresa_id: int):
        """Cada teste termina com a fila da empresa vazia."""
        yield
        with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,)
            )

    def test_1_default_da_migration_e_8s(self, db_url: str, conexao_id: int) -> None:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resposta_agrupamento_segundos FROM conexao WHERE id = %s",
                (conexao_id,),
            )
            row = cur.fetchone()
        assert row is not None, "conexão sumiu"
        assert row[0] == 8, f"default da mig 144 deveria ser 8s, veio {row[0]}"

    def test_2_primeira_mensagem_tambem_espera_a_janela(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """A janela é UNIFORME — vale inclusive pra 1ª mensagem do turno.

        A fase 1 dava 2s à primeira pra respondê-la na hora, e era isso que
        deixava o fragmento passar: a row era reivindicada antes do "Boa tarde!"
        chegar, e row reivindicada não aceita merge.
        """
        loop, p = pool
        loop.run_until_complete(
            _enqueue(
                p,
                phone_number=_PHONE,
                agent_id=_AGENT,
                body="Oi",
                empresa_id=empresa_id,
                conexao_id=conexao_id,
                buffer_seconds=2.0,
                grouping_seconds=8.0,
            )
        )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXTRACT(EPOCH FROM (process_after - created_at))
                  FROM message_queue WHERE empresa_id = %s
                """,
                (empresa_id,),
            )
            row = cur.fetchone()
        assert row is not None, "nada foi enfileirado"
        assert 7.0 <= float(row[0]) <= 8.5, (
            f"1ª mensagem deveria usar a janela uniforme de 8s, esperou {row[0]}s"
        )

    def test_3_mensagens_seguidas_viram_uma_row(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        loop, p = pool
        for texto in ("Oi", "bom dia", "queria saber de X"):
            loop.run_until_complete(
                _enqueue(
                    p,
                    phone_number=_PHONE,
                    agent_id=_AGENT,
                    body=texto,
                    empresa_id=empresa_id,
                    conexao_id=conexao_id,
                    buffer_seconds=2.0,
                    grouping_seconds=8.0,
                )
            )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT incoming_message FROM message_queue WHERE empresa_id = %s",
                (empresa_id,),
            )
            rows = cur.fetchall()
        assert len(rows) == 1, f"esperava 1 row agrupada, vieram {len(rows)}"
        assert rows[0][0] == "Oi\nbom dia\nqueria saber de X"

    def test_4_teto_limita_a_espera(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """Com teto de 5s, o lote não pode ser empurrado além disso."""
        loop, p = pool
        for texto in ("a", "b", "c", "d"):
            loop.run_until_complete(
                _enqueue(
                    p,
                    phone_number=_PHONE,
                    agent_id=_AGENT,
                    body=texto,
                    empresa_id=empresa_id,
                    conexao_id=conexao_id,
                    buffer_seconds=2.0,
                    grouping_seconds=8.0,
                    grouping_max_seconds=5.0,
                )
            )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXTRACT(EPOCH FROM (process_after - created_at))
                  FROM message_queue WHERE empresa_id = %s
                """,
                (empresa_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert float(row[0]) <= 5.5, f"teto de 5s furado: {row[0]}s"

    def test_5_patch_pela_api_persiste(
        self, db_url: str, empresa_id: int, conexao_id: int
    ) -> None:
        headers = {
            **get_admin_api_headers(),
            "X-Empresa-Id": str(empresa_id),
        }
        r = httpx.patch(
            f"{API_BASE_URL}/api/conexoes/{conexao_id}",
            json={"resposta_agrupamento_segundos": 15},
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["resposta_agrupamento_segundos"] == 15

    def test_6_valor_fora_da_faixa_e_rejeitado(
        self, empresa_id: int, conexao_id: int
    ) -> None:
        """0..60 — o CHECK do banco não pode virar 500 na cara do usuário."""
        headers = {
            **get_admin_api_headers(),
            "X-Empresa-Id": str(empresa_id),
        }
        r = httpx.patch(
            f"{API_BASE_URL}/api/conexoes/{conexao_id}",
            json={"resposta_agrupamento_segundos": 999},
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 422, f"esperava 422 do pydantic, veio {r.status_code}"

    def test_7_kill_switch_volta_ao_comportamento_antigo(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """Com 0, cada mensagem vira sua própria row depois da janela curta."""
        loop, p = pool
        loop.run_until_complete(
            _enqueue(
                p,
                phone_number=_PHONE,
                agent_id=_AGENT,
                body="sozinha",
                empresa_id=empresa_id,
                conexao_id=conexao_id,
                buffer_seconds=2.0,
                grouping_seconds=0.0,
            )
        )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXTRACT(EPOCH FROM (process_after - created_at))
                  FROM message_queue WHERE empresa_id = %s
                """,
                (empresa_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert float(row[0]) <= 2.5

    # ------------------------------------------------------------------
    # Mídia no object storage (migs 183/184): `media_url` fica NULL e só
    # `media_arquivo_uuid` é gravado. As queries de "texto pendente" do
    # debounce filtravam por `media_url IS NULL` — e viam a mídia do bucket
    # como texto. Achado em 2026-09-17 na varredura pós-PR #136.
    # ------------------------------------------------------------------

    def _enqueue_audio_no_bucket(self, loop, p, empresa_id, conexao_id, uuid_):
        return loop.run_until_complete(
            _enqueue(
                p,
                phone_number=_PHONE,
                agent_id=_AGENT,
                body="",
                media_url=None,
                media_type="audio/ogg; codecs=opus",
                media_arquivo_uuid=uuid_,
                empresa_id=empresa_id,
                conexao_id=conexao_id,
                buffer_seconds=2.0,
                grouping_seconds=8.0,
            )
        )

    def test_8_duas_midias_no_bucket_sobrevivem(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """Dois áudios seguidos dentro da janela: a 2ª mídia absorvia a 1ª
        como se fosse texto pendente (DELETE ... RETURNING) — o 1º áudio sumia
        da fila e da timeline."""
        loop, p = pool
        u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
        self._enqueue_audio_no_bucket(loop, p, empresa_id, conexao_id, u1)
        self._enqueue_audio_no_bucket(loop, p, empresa_id, conexao_id, u2)
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT media_arquivo_uuid::text FROM message_queue "
                "WHERE empresa_id = %s ORDER BY id",
                (empresa_id,),
            )
            rows = [r[0] for r in cur.fetchall()]
        assert rows == [u1, u2], f"esperava os 2 áudios na fila, ficou {rows}"

    def test_9_texto_depois_de_midia_no_bucket_vira_row_propria(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """Áudio no bucket e depois texto: o texto era concatenado DENTRO da
        row do áudio (o SELECT de texto pendente achava a mídia)."""
        loop, p = pool
        u1 = str(uuid.uuid4())
        self._enqueue_audio_no_bucket(loop, p, empresa_id, conexao_id, u1)
        loop.run_until_complete(
            _enqueue(
                p,
                phone_number=_PHONE,
                agent_id=_AGENT,
                body="e aí, ouviu?",
                empresa_id=empresa_id,
                conexao_id=conexao_id,
                buffer_seconds=2.0,
                grouping_seconds=8.0,
            )
        )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT media_arquivo_uuid::text, incoming_message FROM message_queue "
                "WHERE empresa_id = %s ORDER BY id",
                (empresa_id,),
            )
            rows = cur.fetchall()
        assert rows == [(u1, ""), (None, "e aí, ouviu?")], rows

    def test_10_midia_nao_faz_flush_de_midia_com_agrupamento_desligado(
        self, pool, empresa_id: int, conexao_id: int
    ) -> None:
        """Kill-switch (grouping 0): o flush antecipa só TEXTO pendente; a
        mídia do bucket que ainda espera não pode ter o process_after mexido."""
        loop, p = pool
        u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
        self._enqueue_audio_no_bucket(loop, p, empresa_id, conexao_id, u1)
        loop.run_until_complete(
            _enqueue(
                p,
                phone_number=_PHONE,
                agent_id=_AGENT,
                body="",
                media_url=None,
                media_type="image/jpeg",
                media_arquivo_uuid=u2,
                empresa_id=empresa_id,
                conexao_id=conexao_id,
                buffer_seconds=2.0,
                grouping_seconds=0.0,
            )
        )
        with psycopg.connect(get_db_url()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT media_arquivo_uuid::text, "
                "EXTRACT(EPOCH FROM (process_after - created_at)) "
                "FROM message_queue WHERE empresa_id = %s ORDER BY id",
                (empresa_id,),
            )
            rows = cur.fetchall()
        assert [r[0] for r in rows] == [u1, u2]
        assert float(rows[0][1]) >= 7.0, (
            f"o 1º áudio teve o process_after antecipado: {rows[0][1]}s"
        )
