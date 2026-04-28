"""Matriz de testes de debounce determinísticos.

Valida as regras de debounce da Fase 3:
- Debounce somente para texto.
- Mensagem com mídia não faz debounce (entrada imediata).
- Antes de inserir mídia, flush de texto pendente do mesmo phone+agent.
- Isolamento por agent_id e phone_number.
- Concorrência protegida por pg_advisory_xact_lock.
- Interação correta entre debounce e retry/lease.

Limitação conhecida: NumMedia > 1 no mesmo webhook fora do escopo.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from whatsapp_langchain.shared.queue import enqueue_or_buffer


@pytest.fixture
def mock_pool():
    """Pool mockado com conexão fake via asynccontextmanager.

    Retorna (pool, conn) para inspeção dos SQLs executados.
    """
    conn = AsyncMock()
    pool = AsyncMock()

    @asynccontextmanager
    async def fake_connection():
        yield conn

    pool.connection = fake_connection
    return pool, conn


def lock_cursor():
    """Cursor para pg_advisory_xact_lock (primeira chamada em todas as operações)."""
    return AsyncMock()


def setup_no_existing(conn):
    """Configura mock para: nenhuma mensagem existente (INSERT novo).

    Ordem de executes: [lock, SELECT, INSERT].
    """
    select_cursor = AsyncMock()
    select_cursor.fetchone = AsyncMock(return_value=None)
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(42,))

    conn.execute = AsyncMock(side_effect=[lock_cursor(), select_cursor, insert_cursor])


def setup_existing_text(conn, existing_id=10, existing_body="Oi"):
    """Configura mock para: mensagem de texto existente (debounce).

    Ordem de executes: [lock, SELECT, UPDATE].
    """
    select_cursor = AsyncMock()
    select_cursor.fetchone = AsyncMock(return_value=(existing_id, existing_body))
    update_cursor = AsyncMock()

    conn.execute = AsyncMock(side_effect=[lock_cursor(), select_cursor, update_cursor])


def setup_media_no_pending(conn, new_id=50):
    """Configura mock para mídia: nenhum texto pendente para flush.

    Ordem de executes: [lock, UPDATE(flush), INSERT].
    """
    flush_cursor = AsyncMock()
    flush_cursor.rowcount = 0
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(new_id,))

    conn.execute = AsyncMock(side_effect=[lock_cursor(), flush_cursor, insert_cursor])


def setup_media_with_pending(conn, new_id=50, flushed_count=1):
    """Configura mock para mídia: texto pendente que será flushed.

    Ordem de executes: [lock, UPDATE(flush), INSERT].
    """
    flush_cursor = AsyncMock()
    flush_cursor.rowcount = flushed_count
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(new_id,))

    conn.execute = AsyncMock(side_effect=[lock_cursor(), flush_cursor, insert_cursor])


class TestTextDebounce:
    """Debounce de mensagens de texto (sem mídia)."""

    async def test_first_text_creates_new_entry(self, mock_pool):
        """Primeira mensagem de texto cria nova entrada na fila."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Olá",
        )

        assert result.is_buffered is False
        assert result.message_id == 42

    async def test_rapid_text_concatenates_body(self, mock_pool):
        """Textos rápidos do mesmo phone+agent concatenam no body."""
        pool, conn = mock_pool
        setup_existing_text(conn, existing_id=10, existing_body="Oi")

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Tudo bem?",
        )

        assert result.is_buffered is True
        assert result.message_id == 10

        # calls[0]=lock, calls[1]=SELECT, calls[2]=UPDATE
        calls = conn.execute.call_args_list
        update_sql = calls[2][0][0]
        update_params = calls[2][0][1]
        assert "incoming_message" in update_sql
        assert "process_after" in update_sql
        # Body concatenado com \n
        assert update_params[0] == "Oi\nTudo bem?"

    async def test_triple_text_concatenation_order(self, mock_pool):
        """Três textos rápidos concatenam na ordem correta."""
        pool, conn = mock_pool
        setup_existing_text(conn, existing_id=10, existing_body="Oi\nTudo bem?")

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Como vai?",
        )

        assert result.is_buffered is True
        # calls[0]=lock, calls[1]=SELECT, calls[2]=UPDATE
        calls = conn.execute.call_args_list
        update_params = calls[2][0][1]
        assert update_params[0] == "Oi\nTudo bem?\nComo vai?"

    async def test_text_debounce_resets_timer(self, mock_pool):
        """Debounce reseta o process_after para o novo buffer."""
        pool, conn = mock_pool
        setup_existing_text(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Mais texto",
            buffer_seconds=3.0,
        )

        # calls[0]=lock, calls[1]=SELECT, calls[2]=UPDATE
        calls = conn.execute.call_args_list
        update_sql = calls[2][0][0]
        assert "process_after = %s" in update_sql

    async def test_select_only_text_messages(self, mock_pool):
        """Query de debounce filtra por media_url IS NULL."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Texto",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[1][0][0]
        assert "media_url IS NULL" in select_sql

    async def test_text_insert_has_null_media(self, mock_pool):
        """Inserção de texto sempre tem media_url=NULL e media_type=NULL."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Texto puro",
        )

        # calls[0]=lock, calls[1]=SELECT, calls[2]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[2][0][1]
        # media_url e media_type devem ser None na inserção de texto
        assert insert_params[6] is None  # media_url
        assert insert_params[7] is None  # media_type


class TestMediaNoDebounce:
    """Mensagens com mídia não fazem debounce."""

    async def test_media_inserts_immediately(self, mock_pool):
        """Mídia é inserida com process_after=NOW() (sem buffer)."""
        pool, conn = mock_pool
        setup_media_no_pending(conn, new_id=50)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        assert result.is_buffered is False
        assert result.message_id == 50

        # calls[0]=lock, calls[1]=UPDATE(flush), calls[2]=INSERT
        calls = conn.execute.call_args_list
        insert_sql = calls[2][0][0]
        assert "process_after" in insert_sql
        assert "NOW()" in insert_sql

    async def test_media_never_concatenates(self, mock_pool):
        """Mídia nunca é concatenada com mensagem existente."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Foto do recibo",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush), calls[2]=INSERT
        calls = conn.execute.call_args_list
        assert len(calls) == 3
        flush_sql = calls[1][0][0]
        insert_sql = calls[2][0][0]
        assert "UPDATE" in flush_sql  # flush
        assert "INSERT" in insert_sql  # insert direto

    async def test_media_preserves_body_text(self, mock_pool):
        """Mídia com texto no body preserva o texto na inserção."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Olha essa foto",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush), calls[2]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[2][0][1]
        # Body é preservado na mídia
        assert insert_params[5] == "Olha essa foto"
        # media_url e media_type presentes
        assert insert_params[6] == "https://api.twilio.com/media/img.jpg"
        assert insert_params[7] == "image/jpeg"


class TestMediaFlushPendingText:
    """Flush de texto pendente antes de inserir mídia."""

    async def test_flush_sets_process_after_now(self, mock_pool):
        """Flush atualiza process_after=NOW() para texto pendente."""
        pool, conn = mock_pool
        setup_media_with_pending(conn, flushed_count=1)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush), calls[2]=INSERT
        calls = conn.execute.call_args_list
        flush_sql = calls[1][0][0]
        flush_params = calls[1][0][1]

        # SQL de flush: process_after = NOW() apenas para texto pendente
        assert "SET process_after = NOW()" in flush_sql
        assert "status = 'queued'" in flush_sql
        assert "process_after > NOW()" in flush_sql
        assert "media_url IS NULL" in flush_sql
        # Params: phone_number, agent_id
        assert flush_params == ("+5511999999999", "assistant")

    async def test_flush_only_same_phone_and_agent(self, mock_pool):
        """Flush é isolado por phone_number + agent_id."""
        pool, conn = mock_pool
        setup_media_with_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511111111111",
            agent_id="bot_a",
            body="",
            media_url="https://api.twilio.com/media/audio.ogg",
            media_type="audio/ogg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush)
        calls = conn.execute.call_args_list
        flush_params = calls[1][0][1]
        assert flush_params == ("+5511111111111", "bot_a")

    async def test_no_pending_text_skips_flush_log(self, mock_pool):
        """Se não há texto pendente, flush é no-op (rowcount=0)."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        # Mídia é inserida normalmente
        assert result.is_buffered is False

    async def test_flush_does_not_affect_queued_media(self, mock_pool):
        """Regressão: flush não antecipa mídia queued, apenas texto."""
        pool, conn = mock_pool
        setup_media_with_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://api.twilio.com/media/img2.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush)
        calls = conn.execute.call_args_list
        flush_sql = calls[1][0][0]
        # Flush restringe a texto: media_url IS NULL impede alterar mídia queued
        assert "media_url IS NULL" in flush_sql


class TestAgentIsolation:
    """Debounce é isolado por agent_id."""

    async def test_different_agents_no_debounce(self, mock_pool):
        """Mensagens para agentes diferentes não fazem debounce."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="bot_b",
            body="Olá bot B",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_params = calls[1][0][1]
        # O SELECT filtra por agent_id
        assert select_params[1] == "bot_b"

    async def test_select_includes_agent_filter(self, mock_pool):
        """Query de debounce inclui filtro por agent_id."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="custom_agent",
            body="Teste",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[1][0][0]
        assert "agent_id = %s" in select_sql


class TestPhoneIsolation:
    """Debounce é isolado por phone_number."""

    async def test_different_phones_no_debounce(self, mock_pool):
        """Mensagens de telefones diferentes não fazem debounce."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5522222222222",
            agent_id="assistant",
            body="Olá",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_params = calls[1][0][1]
        # O SELECT filtra por phone_number
        assert select_params[0] == "+5522222222222"


class TestDebounceWithRetry:
    """Interação entre debounce e retry/lease."""

    async def test_debounce_only_queued_status(self, mock_pool):
        """Debounce só considera mensagens com status='queued'."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Texto",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[1][0][0]
        assert "status = 'queued'" in select_sql

    async def test_debounce_only_future_process_after(self, mock_pool):
        """Debounce só considera mensagens com process_after > NOW()."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Texto",
        )

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[1][0][0]
        assert "process_after > NOW()" in select_sql

    async def test_debounce_ignores_processing_messages(self, mock_pool):
        """Mensagens em processing não participam do debounce."""
        pool, conn = mock_pool
        # Mock retorna None (nenhuma mensagem queued encontrada)
        # Mesmo que existam mensagens em processing, o SELECT filtra
        setup_no_existing(conn)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Texto",
        )

        # Cria nova entrada (não debounce com processing)
        assert result.is_buffered is False


class TestSequentialTextThenMedia:
    """Cenário: texto seguido de mídia do mesmo usuário."""

    async def test_text_then_media_flushes_text(self, mock_pool):
        """Quando mídia chega após texto, o texto pendente é flushed."""
        pool, conn = mock_pool
        setup_media_with_pending(conn, new_id=51, flushed_count=1)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Foto",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=lock, calls[1]=UPDATE(flush), calls[2]=INSERT
        calls = conn.execute.call_args_list
        assert len(calls) == 3

        flush_sql = calls[1][0][0]
        assert "SET process_after = NOW()" in flush_sql

        insert_sql = calls[2][0][0]
        assert "INSERT" in insert_sql
        assert result.message_id == 51

    async def test_media_then_text_no_debounce_into_media(self, mock_pool):
        """Texto após mídia não debounce na mídia (media_url IS NULL)."""
        pool, conn = mock_pool
        # SELECT não encontra nada (mídia tem process_after=NOW()
        # e/ou media_url IS NOT NULL)
        setup_no_existing(conn)

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Descreva a imagem",
        )

        assert result.is_buffered is False

        # calls[0]=lock, calls[1]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[1][0][0]
        assert "media_url IS NULL" in select_sql


class TestThreadIdGeneration:
    """Thread ID é gerado como phone:agent_id."""

    async def test_thread_id_format(self, mock_pool):
        """Thread ID segue formato 'phone:agent_id'."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="rhawk_assistant",
            body="Olá",
        )

        # calls[0]=lock, calls[1]=SELECT, calls[2]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[2][0][1]
        # thread_id é o 5o param (index 4)
        assert insert_params[4] == "+5511999999999:rhawk_assistant"


class TestAdvisoryLock:
    """Concorrência protegida por pg_advisory_xact_lock."""

    async def test_lock_called_before_any_operation(self, mock_pool):
        """Advisory lock é a primeira chamada dentro da transação."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Olá",
        )

        calls = conn.execute.call_args_list
        lock_sql = calls[0][0][0]
        assert "pg_advisory_xact_lock" in lock_sql

    async def test_lock_uses_deterministic_key(self, mock_pool):
        """Chave do lock é determinística para o mesmo phone+agent."""
        import hashlib

        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Olá",
        )

        calls = conn.execute.call_args_list
        lock_key = calls[0][0][1][0]

        # Calcula o esperado
        thread_id = "+5511999999999:assistant"
        expected = int.from_bytes(
            hashlib.sha256(thread_id.encode()).digest()[:8],
            byteorder="big",
            signed=True,
        )
        assert lock_key == expected

    async def test_different_phone_different_lock(self, mock_pool):
        """Phones diferentes geram locks diferentes."""
        import hashlib

        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5522222222222",
            agent_id="assistant",
            body="Olá",
        )

        calls = conn.execute.call_args_list
        lock_key = calls[0][0][1][0]

        # Lock de outro phone deve ser diferente
        other_thread = "+5511999999999:assistant"
        other_key = int.from_bytes(
            hashlib.sha256(other_thread.encode()).digest()[:8],
            byteorder="big",
            signed=True,
        )
        assert lock_key != other_key

    async def test_media_also_acquires_lock(self, mock_pool):
        """Mídia também adquire advisory lock antes do flush."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://api.twilio.com/media/img.jpg",
            media_type="image/jpeg",
        )

        calls = conn.execute.call_args_list
        lock_sql = calls[0][0][0]
        assert "pg_advisory_xact_lock" in lock_sql
