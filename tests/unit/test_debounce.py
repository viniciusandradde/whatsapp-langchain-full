"""Matriz de testes de debounce determinísticos.

Valida as regras de debounce da Fase 3:
- Debounce somente para texto.
- Isolamento por agent_id e phone_number.
- Concorrência protegida por pg_advisory_xact_lock.
- Interação correta entre debounce e retry/lease.

E o agrupamento da mig 144 (`TestJanelaAdaptativa` em diante):
- Janela UNIFORME: toda mensagem espera, inclusive a 1ª.
- Fluxo guiado (menu/coleta/CSAT) nunca alonga.
- Teto limita cliente tagarela.
- `grouping_seconds=0` reproduz o comportamento anterior (kill switch).
- Mídia absorve o texto pendente em vez de flushar — texto+áudio viram uma
  resposta só. Com o agrupamento desligado, volta a flushar como antes.
- `existe_mensagem_mais_nova` engole a resposta que nasceu velha, cobrindo o
  intervalo entre reivindicar a row e o envio (~7s), fora do alcance do debounce.

Múltiplas mídias (NumMedia > 1) seguem como N rows independentes com o mesmo
message_id, processadas em ordem de created_at pelo worker.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from whatsapp_langchain.shared.queue import (
    absorver_pendentes,
    chave_lock_conversa,
    detectar_fluxo_guiado,
    enqueue_or_buffer,
    existe_mensagem_mais_nova,
)


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
    """Cursor para pg_advisory_xact_lock (segunda chamada em todas as operações)."""
    return AsyncMock()


def setconfig_cursor():
    """Cursor para set_config (RLS context — primeira chamada, Sprint A.2.3)."""
    return AsyncMock()


def setup_no_existing(conn):
    """Configura mock para: nenhuma mensagem existente (INSERT novo).

    Ordem de executes: [set_config, lock, SELECT, INSERT].
    """
    select_cursor = AsyncMock()
    select_cursor.fetchone = AsyncMock(return_value=None)
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(42,))

    conn.execute = AsyncMock(
        side_effect=[setconfig_cursor(), lock_cursor(), select_cursor, insert_cursor]
    )


def setup_existing_text(conn, existing_id=10, existing_body="Oi", created_at=None):
    """Configura mock para: mensagem de texto existente (debounce).

    Ordem de executes: [set_config, lock, SELECT, UPDATE].

    O SELECT devolve `created_at` desde a mig 144 — é o início do lote, usado
    pra aplicar o teto de espera.
    """
    select_cursor = AsyncMock()
    select_cursor.fetchone = AsyncMock(
        return_value=(existing_id, existing_body, created_at or datetime.now(UTC))
    )
    update_cursor = AsyncMock()

    conn.execute = AsyncMock(
        side_effect=[setconfig_cursor(), lock_cursor(), select_cursor, update_cursor]
    )


def setup_media_no_pending(conn, new_id=50):
    """Configura mock para mídia: nenhum texto pendente para flush.

    Ordem de executes: [set_config, lock, UPDATE(flush), INSERT].
    """
    flush_cursor = AsyncMock()
    flush_cursor.rowcount = 0
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(new_id,))

    conn.execute = AsyncMock(
        side_effect=[setconfig_cursor(), lock_cursor(), flush_cursor, insert_cursor]
    )


def setup_media_with_pending(conn, new_id=50, flushed_count=1):
    """Configura mock para mídia: texto pendente que será flushed.

    Ordem de executes: [set_config, lock, UPDATE(flush), INSERT].
    """
    flush_cursor = AsyncMock()
    flush_cursor.rowcount = flushed_count
    insert_cursor = AsyncMock()
    insert_cursor.fetchone = AsyncMock(return_value=(new_id,))

    conn.execute = AsyncMock(
        side_effect=[setconfig_cursor(), lock_cursor(), flush_cursor, insert_cursor]
    )


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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT, calls[3]=UPDATE
        calls = conn.execute.call_args_list
        update_sql = calls[3][0][0]
        update_params = calls[3][0][1]
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
        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT, calls[3]=UPDATE
        calls = conn.execute.call_args_list
        update_params = calls[3][0][1]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT, calls[3]=UPDATE
        calls = conn.execute.call_args_list
        update_sql = calls[3][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[2][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT, calls[3]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[3][0][1]
        # Ordem do INSERT (M3): empresa_id, conexao_id, atendimento_id,
        # message_id, phone, to, agent, thread, body, media_url, media_type,
        # process_after.
        assert insert_params[0] == 1  # empresa_id default
        assert insert_params[1] is None  # conexao_id (não veio do webhook)
        assert insert_params[2] is None  # atendimento_id (não veio do webhook)
        assert insert_params[9] is None  # media_url
        assert insert_params[10] is None  # media_type


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
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        assert result.is_buffered is False
        assert result.message_id == 50

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush), calls[3]=INSERT
        calls = conn.execute.call_args_list
        insert_sql = calls[3][0][0]
        insert_params = calls[3][0][1]
        assert "process_after" in insert_sql
        # Desde a mig 144 o process_after vai como PARÂMETRO (e não literal
        # NOW()), porque a mídia passou a participar da janela adaptativa.
        # Com o agrupamento desligado o valor é o "agora", como antes.
        assert insert_params[-1] <= datetime.now(UTC)

    async def test_media_never_concatenates(self, mock_pool):
        """Mídia nunca é concatenada com mensagem existente."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Foto do recibo",
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush), calls[3]=INSERT
        calls = conn.execute.call_args_list
        assert len(calls) == 4
        flush_sql = calls[2][0][0]
        insert_sql = calls[3][0][0]
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
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush), calls[3]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[3][0][1]
        # Mesma ordem do texto, sem process_after (mídia usa NOW() inline).
        assert insert_params[0] == 1
        assert insert_params[1] is None  # conexao_id
        assert insert_params[2] is None  # atendimento_id
        assert insert_params[8] == "Olha essa foto"
        assert insert_params[9] == "https://media.example.com/img.jpg"
        assert insert_params[10] == "image/jpeg"


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
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush), calls[3]=INSERT
        calls = conn.execute.call_args_list
        flush_sql = calls[2][0][0]
        flush_params = calls[2][0][1]

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
            media_url="https://media.example.com/audio.ogg",
            media_type="audio/ogg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush)
        calls = conn.execute.call_args_list
        flush_params = calls[2][0][1]
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
            media_url="https://media.example.com/img.jpg",
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
            media_url="https://media.example.com/img2.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush)
        calls = conn.execute.call_args_list
        flush_sql = calls[2][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_params = calls[2][0][1]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[2][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_params = calls[2][0][1]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[2][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[2][0][0]
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
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=UPDATE(flush), calls[3]=INSERT
        calls = conn.execute.call_args_list
        assert len(calls) == 4

        flush_sql = calls[2][0][0]
        assert "SET process_after = NOW()" in flush_sql

        insert_sql = calls[3][0][0]
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

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT
        calls = conn.execute.call_args_list
        select_sql = calls[2][0][0]
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
            agent_id="vsa_tech",
            body="Olá",
        )

        # calls[0]=set_config, calls[1]=lock, calls[2]=SELECT, calls[3]=INSERT
        calls = conn.execute.call_args_list
        insert_params = calls[3][0][1]
        # thread_id na index 7 — empresa_id [0], conexao_id [1], atendimento_id [2].
        assert insert_params[7] == "+5511999999999:vsa_tech"


class TestAdvisoryLock:
    """Concorrência protegida por pg_advisory_xact_lock."""

    async def test_lock_called_before_any_operation(self, mock_pool):
        """Advisory lock vem logo após o set_config do RLS context."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Olá",
        )

        # calls[0]=set_config (RLS), calls[1]=lock
        calls = conn.execute.call_args_list
        lock_sql = calls[1][0][0]
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
        lock_key = calls[1][0][1][0]

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
        lock_key = calls[1][0][1][0]

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
            media_url="https://media.example.com/img.jpg",
            media_type="image/jpeg",
        )

        # calls[0]=set_config, calls[1]=lock
        calls = conn.execute.call_args_list
        lock_sql = calls[1][0][0]
        assert "pg_advisory_xact_lock" in lock_sql


class TestMultiMediaIdempotency:
    """Idempotência do flush em cenários NumMedia > 1.

    Quando o webhook envia N mídias, enqueue_or_buffer é chamado N vezes.
    A primeira chamada faz flush do texto pendente; as subsequentes são
    no-op no flush (rowcount=0) e apenas inserem a mídia diretamente.
    """

    async def test_segunda_midia_nao_interfere_com_flush(self, mock_pool):
        """Segunda mídia não re-faz flush (texto já foi flushed pela primeira).

        Simula cenário: texto pendente → mídia1 (flush+insert) → mídia2 (só insert).
        O UPDATE de flush deve ser idempotente: na segunda chamada rowcount=0.
        """
        pool, conn = mock_pool

        # --- Chamada 1: mídia com texto pendente para flushar ---
        setup_media_with_pending(conn, new_id=51, flushed_count=1)
        result1 = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://example.com/img0.jpg",
            media_type="image/jpeg",
        )
        calls_after_first = conn.execute.call_args_list[:]

        # calls: set_config, lock, UPDATE(flush com rowcount=1), INSERT
        assert len(calls_after_first) == 4
        flush_sql_1 = calls_after_first[2][0][0]
        assert "SET process_after = NOW()" in flush_sql_1
        assert result1.is_buffered is False
        assert result1.message_id == 51

        # --- Chamada 2: segunda mídia (sem texto pendente) ---
        setup_media_no_pending(conn, new_id=52)
        conn.execute.reset_mock()
        result2 = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://example.com/img1.jpg",
            media_type="image/jpeg",
        )
        calls_after_second = conn.execute.call_args_list[:]

        # calls: set_config, lock, UPDATE(flush no-op com rowcount=0), INSERT
        assert len(calls_after_second) == 4
        flush_sql_2 = calls_after_second[2][0][0]
        assert "SET process_after = NOW()" in flush_sql_2  # mesmo SQL
        assert result2.is_buffered is False
        assert result2.message_id == 52

        # As duas mídias são inseridas com media_url distintas (index 9
        # após inclusão de empresa_id [0], conexao_id [1], atendimento_id [2]).
        insert_params_1 = calls_after_first[3][0][1]
        insert_params_2 = calls_after_second[3][0][1]
        assert insert_params_1[9] == "https://example.com/img0.jpg"
        assert insert_params_2[9] == "https://example.com/img1.jpg"

    async def test_duas_midias_sem_texto_pendente(self, mock_pool):
        """Duas mídias sem texto pendente: cada uma faz flush no-op + insert."""
        pool, conn = mock_pool

        # Chamada 1: sem texto pendente
        setup_media_no_pending(conn, new_id=60)
        result1 = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://example.com/a.jpg",
            media_type="image/jpeg",
        )
        assert result1.message_id == 60
        assert result1.is_buffered is False

        # Chamada 2: também sem texto pendente
        setup_media_no_pending(conn, new_id=61)
        conn.execute.reset_mock()
        result2 = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://example.com/b.jpg",
            media_type="image/jpeg",
        )
        assert result2.message_id == 61
        assert result2.is_buffered is False

        # Cada chamada faz 4 executes: set_config, lock, flush(no-op), insert
        assert conn.execute.call_count == 4


# ---------------------------------------------------------------------------
# Janela adaptativa de agrupamento (mig 144)
# ---------------------------------------------------------------------------


def setup_janela(conn, *, existing=None, new_id=42):
    """Mock pro caminho com agrupamento LIGADO.

    Ordem de executes: [set_config, lock, SELECT(pendente), INSERT|UPDATE].

    A janela é UNIFORME desde a fase 2 — `_resolver_janela` virou expressão pura
    e o SELECT que detectava follow-up deixou de existir, então o mock tem um
    cursor a menos que na versão anterior.
    """
    pendente_cursor = AsyncMock()
    pendente_cursor.fetchone = AsyncMock(return_value=existing)

    final_cursor = AsyncMock()
    final_cursor.fetchone = AsyncMock(return_value=(new_id,))

    conn.execute = AsyncMock(
        side_effect=[
            setconfig_cursor(),
            lock_cursor(),
            pendente_cursor,
            final_cursor,
        ]
    )


def espera_do_insert(conn) -> float:
    """Segundos entre agora e o `process_after` do último INSERT/UPDATE."""
    params = conn.execute.call_args_list[-1][0][1]
    process_after = next(p for p in params if isinstance(p, datetime))
    return (process_after - datetime.now(UTC)).total_seconds()


class TestJanelaAdaptativa:
    """Janela uniforme de agrupamento, por conexão."""

    async def test_janela_e_uniforme_inclusive_na_primeira(self, mock_pool):
        """TODA mensagem espera `grouping_seconds`, inclusive a 1ª do turno.

        A versão anterior dava 2s à primeira e 8s às de follow-up. Medido em
        produção, era isso que deixava o fragmento passar: a row era reivindicada
        em 2s e o "Boa tarde!" que chegava em 6,4s não tinha mais onde mesclar.
        """
        pool, conn = mock_pool
        setup_janela(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Oi",
            buffer_seconds=2.0,
            grouping_seconds=8.0,
        )

        assert 7.0 < espera_do_insert(conn) <= 8.0

    async def test_fluxo_guiado_nunca_alonga(self, mock_pool):
        """Menu/coleta/CSAT respondem na hora — decidido sem I/O."""
        pool, conn = mock_pool
        setup_janela(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="1",
            buffer_seconds=2.0,
            grouping_seconds=8.0,
            is_guided_flow=True,
        )

        assert 1.0 < espera_do_insert(conn) <= 2.0
        # set_config, lock, SELECT(pendente), INSERT — a decisão da janela não
        # consulta o banco.
        assert conn.execute.call_count == 4

    async def test_teto_limita_cliente_tagarela(self, mock_pool):
        """Lote aberto há 43s não pode ser empurrado além do teto de 45s."""
        pool, conn = mock_pool
        aberto_ha_43s = datetime.now(UTC) - timedelta(seconds=43)
        setup_janela(conn, existing=(10, "Oi", aberto_ha_43s))

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="mais",
            buffer_seconds=2.0,
            grouping_seconds=8.0,
            grouping_max_seconds=45.0,
        )

        # A janela pediria +8s; o teto corta em ~2s (45 - 43).
        assert 0 < espera_do_insert(conn) <= 2.5

    async def test_desligado_reproduz_comportamento_anterior(self, mock_pool):
        """`grouping_seconds=0` é o kill switch: nada de SELECT extra."""
        pool, conn = mock_pool
        setup_no_existing(conn)

        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="Oi",
            buffer_seconds=2.0,
            grouping_seconds=0.0,
        )

        # set_config, lock, SELECT(pendente), INSERT — igual à mig anterior
        assert conn.execute.call_count == 4
        assert 1.0 < espera_do_insert(conn) <= 2.0


class TestMidiaAbsorveTexto:
    """Texto + áudio viram UM turno, em vez de duas respostas."""

    async def test_midia_absorve_texto_pendente(self, mock_pool):
        """O texto pendente vira o body da row de mídia e a row some."""
        pool, conn = mock_pool
        delete_cursor = AsyncMock()
        delete_cursor.fetchone = AsyncMock(
            return_value=("Oi, tudo bem?", datetime.now(UTC))
        )
        insert_cursor = AsyncMock()
        insert_cursor.fetchone = AsyncMock(return_value=(50,))

        conn.execute = AsyncMock(
            side_effect=[
                setconfig_cursor(),
                lock_cursor(),
                delete_cursor,
                insert_cursor,
            ]
        )

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_url="https://example.com/audio.ogg",
            media_type="audio/ogg",
            grouping_seconds=8.0,
        )

        assert result.message_id == 50
        # O DELETE ... RETURNING é atômico: sem SELECT separado, senão o
        # worker poderia reivindicar a row entre as duas queries.
        assert "DELETE FROM message_queue" in conn.execute.call_args_list[2][0][0]
        # O texto absorvido entrou no body da mídia.
        assert conn.execute.call_args_list[-1][0][1][8] == "Oi, tudo bem?"

    async def test_midia_sem_texto_pendente_segue_sozinha(self, mock_pool):
        """Sem texto pendente (ou worker chegou antes), mídia é row própria."""
        pool, conn = mock_pool
        delete_cursor = AsyncMock()
        delete_cursor.fetchone = AsyncMock(return_value=None)
        insert_cursor = AsyncMock()
        insert_cursor.fetchone = AsyncMock(return_value=(51,))

        conn.execute = AsyncMock(
            side_effect=[
                setconfig_cursor(),
                lock_cursor(),
                delete_cursor,
                insert_cursor,
            ]
        )

        result = await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="legenda",
            media_url="https://example.com/a.jpg",
            media_type="image/jpeg",
            grouping_seconds=8.0,
        )

        assert result.message_id == 51
        assert conn.execute.call_args_list[-1][0][1][8] == "legenda"


class TestDeteccaoFluxoGuiado:
    """`detectar_fluxo_guiado` — o sinal que isenta menu/coleta/CSAT."""

    async def test_wizard_de_coleta_em_curso(self, mock_pool):
        """`coleta_estado` decide sem ir ao banco."""
        pool, conn = mock_pool
        from whatsapp_langchain.shared.models import Atendimento

        atd = Atendimento(
            id=1,
            empresa_id=1,
            cliente_id=1,
            last_message_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            coleta_estado={"item_id": 3, "idx": 1},
        )

        assert await detectar_fluxo_guiado(
            pool, phone_number="+55", agent_id="a", atendimento=atd
        )
        conn.execute.assert_not_called()

    async def test_csat_aguardando_nota(self, mock_pool):
        """CSAT pendente também decide sem query."""
        pool, conn = mock_pool
        from whatsapp_langchain.shared.models import Atendimento

        atd = Atendimento(
            id=1,
            empresa_id=1,
            cliente_id=1,
            last_message_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            aguardando_avaliacao_at=datetime.now(UTC),
        )

        assert await detectar_fluxo_guiado(
            pool, phone_number="+55", agent_id="a", atendimento=atd
        )
        conn.execute.assert_not_called()

    @pytest.mark.parametrize(
        ("origem", "guiado"),
        [("menu", True), ("workflow", True), ("csat", True), ("agente", False)],
    )
    async def test_ultima_origem_decide(self, mock_pool, origem, guiado):
        """Sem estado no atendimento, vale a origem da última resposta."""
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(origem,))
        conn.execute = AsyncMock(return_value=cursor)

        assert (
            await detectar_fluxo_guiado(pool, phone_number="+55", agent_id="a")
            is guiado
        )

    async def test_thread_sem_resposta_previa_nao_e_guiado(self, mock_pool):
        """Conversa nova: nada carimbado ainda → não é fluxo guiado."""
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value=cursor)

        assert not await detectar_fluxo_guiado(pool, phone_number="+55", agent_id="a")


class TestSupersede:
    """`existe_mensagem_mais_nova` — mata a resposta que nasceu velha.

    O agrupamento no enqueue não cobre o intervalo entre a row ser reivindicada
    e a resposta sair (~7s em produção). Mensagem que chega nesse buraco não
    mescla mais, e virava uma resposta por fragmento.
    """

    async def test_mensagem_mais_nova_na_fila_suprime(self, mock_pool):
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(1,))
        conn.execute = AsyncMock(return_value=cursor)

        assert await existe_mensagem_mais_nova(
            pool, phone_number="+55", agent_id="a", message_id=10
        )

    async def test_sem_mensagem_nova_envia(self, mock_pool):
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value=cursor)

        assert not await existe_mensagem_mais_nova(
            pool, phone_number="+55", agent_id="a", message_id=10
        )

    async def test_so_olha_rows_posteriores_e_pendentes(self, mock_pool):
        """`id >` e status pendente — row antiga ou já concluída não suprime."""
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value=cursor)

        await existe_mensagem_mais_nova(
            pool, phone_number="+55", agent_id="a", message_id=10
        )

        sql = conn.execute.call_args_list[-1][0][0]
        assert "id > %s" in sql
        assert "status IN ('queued', 'processing')" in sql

    async def test_falha_no_lookup_envia(self, mock_pool):
        """Fail-safe INVERTIDO: na dúvida envia.

        Resposta duplicada é ruído; resposta engolida por engano é o cliente
        sem atendimento.
        """
        pool, conn = mock_pool
        conn.execute = AsyncMock(side_effect=RuntimeError("conexão caiu"))

        assert not await existe_mensagem_mais_nova(
            pool, phone_number="+55", agent_id="a", message_id=10
        )


class TestMidiaNoBucketNaoEhTextoPendente:
    """Migs 183/184: mídia no object storage tem `media_url` NULL e só
    `media_arquivo_uuid`. As três queries de "texto pendente" precisam excluir
    as duas colunas — filtrando só `media_url IS NULL`, a mídia do bucket era
    vista como texto: apagada pela mídia seguinte (absorção), antecipada pelo
    flush, ou recebendo o texto seguinte concatenado dentro dela."""

    async def test_select_de_debounce_exclui_referencia_ao_bucket(self, mock_pool):
        pool, conn = mock_pool
        setup_no_existing(conn)
        await enqueue_or_buffer(
            pool, phone_number="+5511999999999", agent_id="assistant", body="Oi"
        )
        select_sql = conn.execute.call_args_list[2][0][0]
        assert "media_url IS NULL" in select_sql
        assert "media_arquivo_uuid IS NULL" in select_sql

    async def test_flush_exclui_referencia_ao_bucket(self, mock_pool):
        """Agrupamento desligado: o UPDATE de flush só pode antecipar texto."""
        pool, conn = mock_pool
        setup_media_no_pending(conn)
        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_arquivo_uuid="11111111-1111-1111-1111-111111111111",
            media_type="audio/ogg",
            grouping_seconds=0.0,
        )
        flush_sql = conn.execute.call_args_list[2][0][0]
        assert "UPDATE" in flush_sql
        assert "media_arquivo_uuid IS NULL" in flush_sql

    async def test_absorcao_exclui_referencia_ao_bucket(self, mock_pool):
        """Agrupamento ligado: o DELETE ... RETURNING só pode absorver texto."""
        pool, conn = mock_pool
        delete_cursor = AsyncMock()
        delete_cursor.fetchone = AsyncMock(return_value=None)
        insert_cursor = AsyncMock()
        insert_cursor.fetchone = AsyncMock(return_value=(51,))
        conn.execute = AsyncMock(
            side_effect=[
                setconfig_cursor(),
                lock_cursor(),
                delete_cursor,
                insert_cursor,
            ]
        )
        await enqueue_or_buffer(
            pool,
            phone_number="+5511999999999",
            agent_id="assistant",
            body="",
            media_arquivo_uuid="22222222-2222-2222-2222-222222222222",
            media_type="audio/ogg",
            grouping_seconds=8.0,
        )
        delete_sql = conn.execute.call_args_list[2][0][0]
        assert "DELETE FROM message_queue" in delete_sql
        assert "media_arquivo_uuid IS NULL" in delete_sql


class TestAbsorverPendentes:
    """`absorver_pendentes` — o fragmento que chega entre o claim e a IA entra
    no turno atual, em vez de virar um segundo turno cuja resposta engole a
    nossa. Medido em produção: 13,6 % dos turnos de IA."""

    async def test_sem_pendente_devolve_vazio_e_nao_escreve(self, mock_pool):
        pool, conn = mock_pool
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=cursor)

        assert (
            await absorver_pendentes(
                pool, phone_number="+55", agent_id="a", message_id=10
            )
            == []
        )
        sqls = [c[0][0] for c in conn.execute.call_args_list]
        assert not any("UPDATE message_queue" in s for s in sqls)
        conn.rollback.assert_awaited_once()
        conn.commit.assert_not_awaited()

    async def test_lock_da_conversa_antes_do_delete(self, mock_pool):
        """Mesma chave do webhook e do claim: ninguém mescla nem reivindica no meio."""
        pool, conn = mock_pool
        t0 = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(
            return_value=[
                ("C", t0 + timedelta(seconds=2)),
                ("B", t0 + timedelta(seconds=1)),
            ]
        )
        conn.execute = AsyncMock(return_value=cursor)

        textos = await absorver_pendentes(
            pool, phone_number="+55", agent_id="a", message_id=10
        )

        assert textos == ["B", "C"], "ordem de chegada, não a do RETURNING"
        calls = conn.execute.call_args_list
        assert "pg_advisory_xact_lock" in calls[0][0][0]
        assert calls[0][0][1] == (chave_lock_conversa("+55", "a"),)
        delete_sql = calls[1][0][0]
        assert "DELETE FROM message_queue" in delete_sql
        assert "id > %s" in delete_sql
        assert "status = 'queued'" in delete_sql
        assert "media_url IS NULL" in delete_sql
        assert "media_arquivo_uuid IS NULL" in delete_sql
        update_sql, update_params = calls[2][0]
        assert "incoming_message = incoming_message || %s" in update_sql
        assert update_params == ("\nB\nC", 10)
        conn.commit.assert_awaited_once()

    async def test_falha_devolve_vazio(self, mock_pool):
        """Fail-safe: sem absorver, o turno segue e o supersede cobre o resto."""
        pool, conn = mock_pool
        conn.execute = AsyncMock(side_effect=RuntimeError("conexão caiu"))

        assert (
            await absorver_pendentes(
                pool, phone_number="+55", agent_id="a", message_id=10
            )
            == []
        )
