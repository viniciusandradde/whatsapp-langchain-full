"""Helpers compartilhados para testes de integração E2E.

Funções utilitárias para interagir com o banco, enviar webhooks,
e aguardar estados terminais durante os testes.

Pré-requisito: stack Docker rodando (make up).
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import psycopg

DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5432/whatsapp_langchain"
API_BASE_URL = "http://localhost:8000"
TEST_INTERNAL_SERVICE_TOKEN = "test-internal-token"


def get_db_url() -> str:
    """Retorna URL de conexão ao banco de dados."""
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


def get_admin_api_headers() -> dict[str, str]:
    """Retorna headers para rotas administrativas protegidas."""
    token = os.getenv("INTERNAL_SERVICE_TOKEN", TEST_INTERNAL_SERVICE_TOKEN)
    return {"Authorization": f"Bearer {token}"}


def unique_phone(ddd: str = "99") -> str:
    """Gera número de telefone único para isolamento entre testes."""
    return f"+55{ddd}{uuid.uuid4().int % 10**8:08d}"


def unique_sid(prefix: str = "SM") -> str:
    """Gera MessageSid único no formato do Twilio."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Consultas ao banco
# ---------------------------------------------------------------------------


def query_message_status(db_url: str, message_sid: str) -> tuple | None:
    """Busca status, response, error e media_type de uma mensagem pelo SID."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, response, error, media_type
                FROM message_queue
                WHERE message_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (message_sid,),
            )
            return cur.fetchone()


def query_conversation(db_url: str, phone_number: str, agent_id: str) -> tuple | None:
    """Busca dados da conversa: message_count, last_message, thread_id."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_count, last_message, thread_id
                FROM conversations
                WHERE phone_number = %s AND agent_id = %s
                """,
                (phone_number, agent_id),
            )
            return cur.fetchone()


def count_queue_entries(
    db_url: str,
    phone_number: str,
    agent_id: str,
    status: str | None = None,
) -> int:
    """Conta entradas na fila para um phone+agent, opcionalmente filtrado por status."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM message_queue
                    WHERE phone_number = %s AND agent_id = %s AND status = %s
                    """,
                    (phone_number, agent_id, status),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM message_queue
                    WHERE phone_number = %s AND agent_id = %s
                    """,
                    (phone_number, agent_id),
                )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def query_queue_entry(db_url: str, phone_number: str, agent_id: str) -> tuple | None:
    """Busca a entrada mais recente da fila: id, incoming_message, status, response."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, incoming_message, status, response
                FROM message_queue
                WHERE phone_number = %s AND agent_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (phone_number, agent_id),
            )
            return cur.fetchone()


def memory_count_for_user(
    db_url: str, user_id: str, contains: str | None = None
) -> int:
    """Conta memórias no store para um usuário, opcionalmente com filtro de conteúdo."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            if contains:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM store
                    WHERE prefix = %s
                      AND value->>'memory' ILIKE %s
                    """,
                    (f"{user_id}.memories", f"%{contains}%"),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM store
                    WHERE prefix = %s
                    """,
                    (f"{user_id}.memories",),
                )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def clear_thread_checkpoints(db_url: str, thread_id: str) -> None:
    """Remove histórico da thread para forçar recall via store."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            cur.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Waits com polling
# ---------------------------------------------------------------------------


def wait_terminal_status(
    db_url: str,
    message_sid: str,
    timeout_seconds: int = 90,
) -> tuple:
    """Aguarda mensagem atingir status terminal (done/failed) via polling."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = query_message_status(db_url, message_sid)
        if row and row[0] in {"done", "failed"}:
            return row
        time.sleep(1)
    raise AssertionError(f"Mensagem {message_sid} não finalizou em {timeout_seconds}s")


def wait_memory_saved(
    db_url: str,
    user_id: str,
    contains: str,
    timeout_seconds: int = 60,
) -> None:
    """Aguarda memória ser salva no store com conteúdo específico."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if memory_count_for_user(db_url, user_id, contains=contains) > 0:
            return
        time.sleep(1)
    raise AssertionError(
        f"Memória com conteúdo '{contains}' não foi encontrada para {user_id}"
    )


def wait_conversation_count(
    db_url: str,
    phone_number: str,
    agent_id: str,
    expected_count: int,
    timeout_seconds: int = 90,
) -> tuple:
    """Aguarda conversations.message_count atingir o valor esperado."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = query_conversation(db_url, phone_number, agent_id)
        if row and row[0] >= expected_count:
            return row
        time.sleep(1)
    raise AssertionError(
        f"Conversa de {phone_number} não atingiu {expected_count} mensagens "
        f"em {timeout_seconds}s"
    )


def wait_queue_done(
    db_url: str,
    phone_number: str,
    agent_id: str,
    timeout_seconds: int = 90,
) -> None:
    """Aguarda mensagens na fila de um phone+agent saírem de queued/processing."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pending = count_queue_entries(db_url, phone_number, agent_id, status="queued")
        processing = count_queue_entries(
            db_url, phone_number, agent_id, status="processing"
        )
        if pending == 0 and processing == 0:
            return
        time.sleep(1)
    raise AssertionError(f"Fila de {phone_number} não esvaziou em {timeout_seconds}s")


# ---------------------------------------------------------------------------
# Envio de webhooks
# ---------------------------------------------------------------------------


def send_webhook(
    phone: str,
    body: str,
    agent: str = "rhawk_assistant",
    message_sid: str | None = None,
    timeout: int = 10,
) -> httpx.Response:
    """Envia POST para /webhook/twilio simulando mensagem do Twilio."""
    sid = message_sid or unique_sid()
    return httpx.post(
        f"{API_BASE_URL}/webhook/twilio?agent={agent}",
        data={
            "MessageSid": sid,
            "From": f"whatsapp:{phone}",
            "To": "whatsapp:+14155238886",
            "Body": body,
            "NumMedia": "0",
        },
        timeout=timeout,
    )


def send_webhook_and_wait(
    db_url: str,
    phone: str,
    body: str,
    agent: str = "rhawk_assistant",
    timeout_seconds: int = 90,
) -> tuple[str, tuple]:
    """Envia webhook e aguarda status terminal. Retorna (sid, row)."""
    sid = unique_sid()
    response = send_webhook(phone, body, agent=agent, message_sid=sid)
    assert response.status_code == 200, f"Webhook retornou {response.status_code}"
    row = wait_terminal_status(db_url, sid, timeout_seconds=timeout_seconds)
    return sid, row
