"""Testes de claim da fila: recuperação de lease e serialização por conversa.

Pool e conexão são mocks; o que se afirma aqui é a SEQUÊNCIA de statements
(expiração → candidato → advisory lock → UPDATE condicionado) e o conteúdo do
SQL. O comportamento contra o Postgres de verdade (dois claims concorrentes na
mesma conversa, deadlock com o webhook) fica em
`tests/integration/test_queue_claim_conversa.py`.
"""

import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_langchain.shared.queue import chave_lock_conversa, claim_next

PHONE = "+5567999990001"
AGENT = "vsa_tech"
AGORA = datetime.now(UTC)


def _row(msg_id: int) -> tuple:
    """Uma row com as 28 colunas do RETURNING, na ordem do mapeamento."""
    return (
        msg_id,  # id
        1,  # empresa_id
        None,  # atendimento_id
        f"wamid.{msg_id}",  # message_id
        PHONE,  # phone_number
        None,  # to_number
        AGENT,  # agent_id
        f"{PHONE}:{AGENT}",  # thread_id
        "oi",  # incoming_message
        None,  # media_url
        None,  # media_type
        None,  # normalized_input
        None,  # media_processing_status
        None,  # media_processing_error
        "processing",  # status
        None,  # process_after
        1,  # attempts
        3,  # max_attempts
        None,  # lease_until
        None,  # response
        None,  # error
        AGORA,  # created_at
        AGORA,  # updated_at
        None,  # processed_at
        None,  # conexao_id
        None,  # conexao_provider
        None,  # media_filename
        None,  # media_arquivo_uuid
    )


def _cursor(fetchone=None) -> AsyncMock:
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=fetchone)
    return cursor


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    pool = AsyncMock()

    @asynccontextmanager
    async def fake_connection():
        yield conn

    pool.connection = fake_connection
    return pool, conn


def _sqls(conn) -> list[str]:
    return [c[0][0] for c in conn.execute.call_args_list]


class TestClaimNextLeaseRecovery:
    """Garante que mensagens não ficam presas em status processing."""

    async def test_marks_expired_processing_as_failed_when_max_attempts_reached(
        self, mock_pool
    ):
        """Lease expirado sem retries restantes deve virar failed."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(side_effect=[_cursor(), _cursor(None)])

        result = await claim_next(pool, lease_seconds=60)

        assert result is None
        sqls = _sqls(conn)
        assert len(sqls) == 2

        stale_sql = sqls[0]
        assert "SET status = 'failed'" in stale_sql
        assert "status = 'processing'" in stale_sql
        assert "lease_until <= NOW()" in stale_sql
        assert "attempts >= max_attempts" in stale_sql

    async def test_reclaims_expired_processing_when_attempts_remain(self, mock_pool):
        """Claim deve considerar processing com lease expirado para retry."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(side_effect=[_cursor(), _cursor(None)])

        result = await claim_next(pool, lease_seconds=60)

        assert result is None
        sqls = _sqls(conn)
        assert len(sqls) == 2

        claim_sql = sqls[1]
        assert "status = 'queued'" in claim_sql
        assert "status = 'processing'" in claim_sql
        assert "lease_until <= NOW()" in claim_sql
        assert "attempts < c.max_attempts" in claim_sql


class TestClaimPorConversa:
    """Uma row em processing por conversa, e o lock é o mesmo do webhook."""

    def test_chave_lock_conversa_igual_ao_enqueue(self):
        """A chave é os 8 bytes iniciais do SHA-256 de `phone:agent`, int64 signed.

        É o contrato entre webhook e claim: se um dos lados mudar a fórmula, os
        dois deixam de se serializar sem nenhum erro visível.
        """
        esperado = int.from_bytes(
            hashlib.sha256(f"{PHONE}:{AGENT}".encode()).digest()[:8],
            byteorder="big",
            signed=True,
        )
        assert chave_lock_conversa(PHONE, AGENT) == esperado
        assert chave_lock_conversa(PHONE, "outro") != esperado

    async def test_fila_vazia_nao_toma_lock(self, mock_pool):
        """Sem candidato não há advisory lock nem UPDATE — e a expiração commitou."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(side_effect=[_cursor(), _cursor(None)])

        assert await claim_next(pool, lease_seconds=60) is None

        sqls = _sqls(conn)
        assert len(sqls) == 2
        assert not any("pg_advisory_xact_lock" in s for s in sqls)
        assert conn.commit.await_count == 2
        conn.rollback.assert_not_awaited()

    async def test_expiracao_commitada_antes_do_lock(self, mock_pool):
        """O UPDATE de expiração trava rows de outras conversas: transação própria."""
        pool, conn = mock_pool
        eventos: list[str] = []

        async def execute(sql, *args):
            eventos.append("lock" if "pg_advisory_xact_lock" in sql else "sql")
            if "SELECT c.id" in sql:
                return _cursor((42, PHONE, AGENT))
            if "UPDATE message_queue AS c" in sql:
                return _cursor(_row(42))
            return _cursor()

        async def commit():
            eventos.append("commit")

        conn.execute = AsyncMock(side_effect=execute)
        conn.commit = AsyncMock(side_effect=commit)

        assert (await claim_next(pool, lease_seconds=60)) is not None
        assert eventos.index("commit") < eventos.index("lock")

    async def test_claim_feliz_lock_antes_do_update(self, mock_pool):
        """Sequência: expiração → candidato → lock da conversa → UPDATE re-checando."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(
            side_effect=[
                _cursor(),  # expiração
                _cursor((42, PHONE, AGENT)),  # candidato
                _cursor(),  # advisory lock
                _cursor(_row(42)),  # UPDATE ... RETURNING
            ]
        )

        result = await claim_next(pool, lease_seconds=60)

        assert result is not None and result.id == 42
        calls = conn.execute.call_args_list
        assert len(calls) == 4

        candidato_sql = calls[1][0][0]
        assert "NOT EXISTS" in candidato_sql
        assert "FOR UPDATE" not in candidato_sql  # ordem de locks: advisory → row

        lock_sql, lock_params = calls[2][0]
        assert "pg_advisory_xact_lock" in lock_sql
        assert lock_params == (chave_lock_conversa(PHONE, AGENT),)

        update_sql, update_params = calls[3][0]
        assert "SET status = 'processing'" in update_sql
        assert "NOT EXISTS" in update_sql
        assert "p.status = 'processing'" in update_sql
        assert "p.lease_until > NOW()" in update_sql
        assert "make_interval(secs => %s)" in update_sql
        assert update_params == (60, 42)
        assert conn.commit.await_count == 2
        conn.rollback.assert_not_awaited()

    async def test_select_candidato_exclui_conversa_ocupada(self, mock_pool):
        """O NOT EXISTS está no SELECT (poupa o lock) E no UPDATE (é a correção)."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(
            side_effect=[
                _cursor(),
                _cursor((42, PHONE, AGENT)),
                _cursor(),
                _cursor(_row(42)),
            ]
        )

        await claim_next(pool, lease_seconds=60)

        sqls = _sqls(conn)
        for sql in (sqls[1], sqls[3]):
            assert "p.phone_number = c.phone_number" in sql
            assert "p.agent_id = c.agent_id" in sql
            assert "p.lease_until > NOW()" in sql

    async def test_update_zero_rows_tenta_proximo_candidato(self, mock_pool):
        """Candidato perdido pra outro slot: rollback, pula o id, tenta o próximo."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(
            side_effect=[
                _cursor(),  # expiração
                _cursor((42, PHONE, AGENT)),  # candidato 1
                _cursor(),  # lock
                _cursor(None),  # UPDATE não afetou: conversa ficou ocupada
                _cursor((43, "+5567999990002", AGENT)),  # candidato 2
                _cursor(),  # lock
                _cursor(_row(43)),  # UPDATE ok
            ]
        )

        result = await claim_next(pool, lease_seconds=60)

        assert result is not None and result.id == 43
        assert conn.rollback.await_count == 1
        segundo_select_params = conn.execute.call_args_list[4][0][1]
        assert segundo_select_params == ([42],)

    async def test_desiste_apos_max_tentativas(self, mock_pool):
        """Perder todos os candidatos devolve None sem lançar; o próximo poll tenta."""
        pool, conn = mock_pool
        tentativa = [_cursor((42, PHONE, AGENT)), _cursor(), _cursor(None)]
        conn.execute = AsyncMock(
            side_effect=[_cursor(), *tentativa, *tentativa, *tentativa]
        )

        result = await claim_next(pool, lease_seconds=60, max_tentativas=3)

        assert result is None
        assert conn.rollback.await_count == 3
        assert sum("SELECT c.id" in s for s in _sqls(conn)) == 3
