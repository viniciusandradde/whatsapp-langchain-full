"""Modelos Pydantic para dados que cruzam fronteiras (API, DB, Worker).

Define as estruturas de dados compartilhadas entre os módulos do projeto.
Todos os modelos usam Pydantic v2 para validação e serialização.

Uso:
    from whatsapp_langchain.shared.models import MessageQueue, MessageStatus

    msg = MessageQueue(phone_number="+5511999999999", agent_id="rhawk_assistant", ...)
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    """Status possíveis de uma mensagem na fila.

    Fluxo: queued → processing → done | failed
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class MessageQueue(BaseModel):
    """Mapeamento da tabela message_queue.

    Representa uma mensagem na fila de processamento.
    O Worker consome mensagens com status 'queued' e as processa.
    """

    id: int
    message_id: str | None = None
    phone_number: str = Field(description="Formato E.164, ex: +5511999999999")
    to_number: str | None = None
    agent_id: str = Field(description="Identificador do agente em langgraph.json")
    thread_id: str = Field(description="ID do thread para checkpointer: phone:agent_id")
    incoming_message: str
    media_url: str | None = None
    media_type: str | None = None
    normalized_input: str | None = None
    media_processing_status: str | None = None
    media_processing_error: str | None = None
    status: MessageStatus = MessageStatus.QUEUED
    process_after: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    lease_until: datetime | None = None
    response: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None


class Conversation(BaseModel):
    """Mapeamento da tabela conversations.

    Agrega dados de uma conversa entre um telefone e um agente.
    Atualizada a cada mensagem processada.
    """

    id: int
    phone_number: str
    agent_id: str
    thread_id: str
    last_message: str
    last_message_at: datetime
    message_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TwilioWebhookPayload(BaseModel):
    """Payload recebido no webhook do Twilio.

    O Twilio envia os dados como form-encoded (application/x-www-form-urlencoded).
    Campos opcionais podem estar ausentes dependendo do tipo de mensagem.
    """

    MessageSid: str = Field(description="ID único da mensagem no Twilio")
    From: str = Field(description="Remetente, ex: whatsapp:+5511999999999")
    To: str = Field(description="Destinatário, ex: whatsapp:+14155238886")
    Body: str = Field(default="", description="Texto da mensagem")
    NumMedia: str = Field(default="0", description="Número de mídias anexadas")
    MediaUrl0: str | None = Field(default=None, description="URL da primeira mídia")
    MediaContentType0: str | None = Field(
        default=None, description="MIME type da primeira mídia"
    )


class EnqueueResult(BaseModel):
    """Resultado de uma operação de enqueue.

    Indica se a mensagem foi inserida na fila ou buffered (debounce).
    """

    message_id: int
    is_buffered: bool = Field(
        default=False,
        description="True se a mensagem foi concatenada a uma existente (debounce)",
    )
