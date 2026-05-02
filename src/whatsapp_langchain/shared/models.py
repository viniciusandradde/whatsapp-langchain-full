"""Modelos Pydantic para dados que cruzam fronteiras (API, DB, Worker).

Define as estruturas de dados compartilhadas entre os módulos do projeto.
Todos os modelos usam Pydantic v2 para validação e serialização.

Uso:
    from whatsapp_langchain.shared.models import MessageQueue, MessageStatus

    msg = MessageQueue(phone_number="+5511999999999", agent_id="vsa_tech", ...)
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
    empresa_id: int = Field(
        default=1, description="Empresa dona da mensagem (multi-tenancy)"
    )
    atendimento_id: int | None = Field(
        default=None,
        description="Atendimento (M3 CRM) ao qual a mensagem pertence; None em rows legacy.",
    )
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


# --- Painel: configuração de modelos LLM por agente ---


class ModelInfo(BaseModel):
    """Item da lista curada de modelos disponíveis no painel."""

    id: str = Field(description="Slug OpenRouter, ex: 'openai/gpt-4o-mini'")
    label: str
    type: str = Field(description="'chat' (principal) ou 'media' (multimodal)")


class AgentLLMConfigResponse(BaseModel):
    """Configuração resolvida de modelos para um agente.

    Os campos `*_model` mostram o valor efetivamente usado (DB ou env), e
    `*_model_override` mostra o valor cru da tabela (None = usa env).
    """

    agent_id: str
    chat_model: str
    midia_model: str
    chat_model_override: str | None
    midia_model_override: str | None


class UpdateAgentLLMConfigRequest(BaseModel):
    """Payload do PUT /api/agents/{id}/config.

    Campos None ou string vazia removem o override (volta a usar env).
    """

    chat_model: str | None = None
    midia_model: str | None = None


# --- Painel: visualização de traces LangSmith ---


class TraceInfo(BaseModel):
    """Run enxuta do LangSmith pra exibir na tabela `/traces` do painel."""

    run_id: str
    name: str | None
    status: str | None
    start_time: str | None
    end_time: str | None
    latency_ms: int | None
    total_tokens: int | None
    thread_id: str | None
    smith_url: str = Field(description="URL direta pro run em smith.langchain.com")


# --- Multi-tenant: Empresa + Membership ---


class Empresa(BaseModel):
    """Tenant root — uma empresa cliente do Nexus Chat AI.

    Toda entidade operacional (conversa, mensagem, conexão, agente) pertence
    a uma `empresa_id`. id=1 é a empresa default "VSA Tech" criada na
    migration 007.

    Quando o response vem de uma listagem do usuário (`list_empresas_of_user`),
    o campo `my_role` é populado com a role do user na empresa.
    """

    id: int
    nome: str
    slug: str
    doc: str | None = None
    plano: str = "free"
    status: str = "active"
    config: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    my_role: str | None = None


class EmpresaMembro(BaseModel):
    """Associa user (Better Auth) a uma empresa com role.

    `is_default=True` marca a empresa que entra automático na sessão quando
    o user não envia X-Empresa-Id. Roles seguem o convention: admin (full
    control), operator (atendimento), viewer (read-only).
    """

    empresa_id: int
    user_id: str
    role: str
    is_default: bool
    joined_at: datetime


# --- Multi-conexão WhatsApp ---


class Conexao(BaseModel):
    """Linha WhatsApp (Twilio sandbox/prod, WABA) ligada a uma empresa.

    O webhook usa `from_number` pra resolver dinamicamente empresa_id +
    default_agent_id. `is_default` marca a conexão preferida pra outbound
    quando a mensagem não cita conexão específica (futuro).
    """

    id: int
    empresa_id: int
    provider: str
    sid: str | None = None
    from_number: str
    display_name: str | None = None
    default_agent_id: str = "vsa_tech"
    status: str = "active"
    is_default: bool = False
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ConexaoInput(BaseModel):
    """Payload de criar/editar conexão (via /api/conexoes)."""

    provider: str
    sid: str | None = None
    from_number: str
    display_name: str | None = None
    default_agent_id: str = "vsa_tech"
    status: str = "active"
    is_default: bool = False
    payload_json: dict = Field(default_factory=dict)


# --- M3 CRM Light: Cliente + Atendimento ---


class Cliente(BaseModel):
    """Pessoa cadastrada na empresa (1 row por empresa+telefone)."""

    id: int
    empresa_id: int
    telefone: str
    nome: str | None = None
    email: str | None = None
    doc: str | None = None
    status: str = "active"
    config: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class ClienteAnotacao(BaseModel):
    id: int
    cliente_id: int
    user_id: str
    conteudo: str
    created_at: datetime


class ModeloMensagem(BaseModel):
    """Texto reutilizável (quick reply) que o operador insere no composer."""

    id: int
    empresa_id: int
    titulo: str
    conteudo: str
    atalho: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ModeloMensagemInput(BaseModel):
    """Payload de POST/PUT em /api/modelos."""

    titulo: str = Field(min_length=1, max_length=120)
    conteudo: str = Field(min_length=1, max_length=4000)
    atalho: str | None = Field(default=None, max_length=64)


class Atendimento(BaseModel):
    """Conversa estruturada — fila de atendimento humano + status."""

    id: int
    empresa_id: int
    cliente_id: int
    conexao_id: int
    agente_atual: str = "vsa_tech"
    status: str = "aguardando"  # aguardando|em_andamento|resolvido|abandonado
    assigned_to_user_id: str | None = None
    last_message_at: datetime
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Campos derivados (preenchidos pelas queries que fazem JOIN):
    cliente_nome: str | None = None
    cliente_telefone: str | None = None
