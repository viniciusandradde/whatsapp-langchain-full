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
        description="Atendimento (M3 CRM); None em rows legacy.",
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


class AgenteIAConfig(BaseModel):
    """Override de comportamento do agente por (empresa, agent_id) — M5.b.

    Quando `ativo` e `system_prompt_override` está preenchido, o loader
    usa este texto em vez do SYSTEM_PROMPT hardcoded no catálogo.
    """

    empresa_id: int
    agent_id: str
    system_prompt_override: str | None = None
    temperatura: float | None = None
    ativo: bool = True
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AgenteIAConfigInput(BaseModel):
    """Payload do PUT /api/agentes/{id}/config-ia.

    `system_prompt_override` vazio + `ativo=False` é o sinal pra "voltar
    pro default" sem precisar deletar a row.
    """

    system_prompt_override: str | None = Field(default=None, max_length=20000)
    temperatura: float | None = Field(default=None, ge=0, le=2)
    ativo: bool = True


class EmpresaCalendarConfig(BaseModel):
    """Conexão Google Calendar de uma empresa (M5.a).

    `oauth_credentials_json` é a serialização do `google.oauth2.credentials
    .Credentials` (token + refresh_token + scopes + expiry). O endpoint
    de OAuth callback persiste isso após troca do code; o tool do agente
    lê + refresh on-demand.
    """

    empresa_id: int
    oauth_credentials_json: dict
    google_email: str | None = None
    calendar_id: str = "primary"
    timezone: str = "America/Sao_Paulo"
    ativo: bool = True
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarConfigPublic(BaseModel):
    """Versão segura pra UI — sem expor o token bruto."""

    empresa_id: int
    google_email: str | None
    calendar_id: str
    timezone: str
    ativo: bool
    created_at: datetime
    updated_at: datetime


HookEvento = str  # validado em runtime contra CHECK constraint da tabela


class Hook(BaseModel):
    """Webhook HTTP configurável da empresa (M4.d).

    Disparado pelo dispatcher quando o evento correspondente acontece;
    cada tentativa fica registrada em `hook_log`.
    """

    id: int
    empresa_id: int
    nome: str
    evento: str
    url: str
    secret: str | None = None
    ativo: bool = True
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class HookInput(BaseModel):
    """Payload de POST/PUT em /api/hooks."""

    nome: str = Field(min_length=1, max_length=120)
    evento: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2048)
    secret: str | None = Field(default=None, max_length=256)
    ativo: bool = True


class HookLog(BaseModel):
    id: int
    hook_id: int
    evento: str
    status_code: int | None = None
    error: str | None = None
    duration_ms: int | None = None
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


class DocumentoConhecimento(BaseModel):
    """Item da base de conhecimento — M5.c (RAG).

    O agente busca top-k docs ativos via tool `search_knowledge_base`
    antes de responder. `embedding` fica fora do payload default (pesado
    e raramente útil pra cliente da API).
    """

    id: int
    empresa_id: int
    titulo: str
    conteudo: str
    tags: list[str] = []
    ativo: bool = True
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentoConhecimentoInput(BaseModel):
    """Payload do POST/PUT /api/empresas/{id}/base-conhecimento."""

    titulo: str = Field(min_length=1, max_length=200)
    conteudo: str = Field(min_length=1, max_length=200000)  # sobe de 20k pra 200k pós-chunking
    tags: list[str] = Field(default_factory=list)
    ativo: bool = True


class DocumentoConhecimentoChunk(BaseModel):
    """Trecho indexado de um documento — M5.c.1."""

    id: int
    documento_id: int
    empresa_id: int
    chunk_idx: int
    conteudo: str
    created_at: datetime


class VariavelAmbiente(BaseModel):
    """KV por empresa referenciado em prompts/modelos como `{{var.NOME}}` — M5.d."""

    id: int
    empresa_id: int
    nome: str
    valor: str
    descricao: str | None = None
    ativo: bool = True
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class VariavelAmbienteInput(BaseModel):
    """Payload do POST/PUT /api/variaveis."""

    nome: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    valor: str = Field(min_length=0, max_length=4000)
    descricao: str | None = Field(default=None, max_length=200)
    ativo: bool = True


class Departamento(BaseModel):
    """Categorização opcional de atendimento (suporte, vendas, etc) — M6.a."""

    id: int
    empresa_id: int
    nome: str
    descricao: str | None = None
    ativo: bool = True
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DepartamentoInput(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    descricao: str | None = Field(default=None, max_length=200)
    ativo: bool = True


class HorarioFuncionamento(BaseModel):
    """Janela de expediente por dia da semana (0=dom .. 6=sáb) — M6.a."""

    id: int
    empresa_id: int
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: str  # "HH:MM" — TIME do Postgres serializa como string
    hora_fim: str
    departamento_id: int | None = None
    ativo: bool = True
    created_at: datetime


class HorarioFuncionamentoInput(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    hora_fim: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    departamento_id: int | None = None
    ativo: bool = True


class Feriado(BaseModel):
    """Override de horário — empresa fechada o dia inteiro — M6.a."""

    id: int
    empresa_id: int
    data: str  # ISO date "YYYY-MM-DD"
    descricao: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime


class FeriadoInput(BaseModel):
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    descricao: str | None = Field(default=None, max_length=200)


# --- M5.b.2 Memória estruturada por cliente ---


class ClienteMemoria(BaseModel):
    """Fato/preferência/perfil de um cliente — buscado semanticamente pelo agente."""

    id: int
    empresa_id: int
    cliente_id: int
    categoria: str  # 'perfil' | 'preferencia' | 'fato'
    conteudo: str
    source: str = "agent_explicit"
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ClienteMemoriaInput(BaseModel):
    categoria: str = Field(pattern=r"^(perfil|preferencia|fato)$")
    conteudo: str = Field(min_length=3, max_length=1000)
    source: str = Field(
        default="agent_explicit",
        pattern=r"^(agent_explicit|agent_extracted|operator)$",
    )
