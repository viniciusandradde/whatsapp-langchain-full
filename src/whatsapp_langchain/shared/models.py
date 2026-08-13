"""Modelos Pydantic para dados que cruzam fronteiras (API, DB, Worker).

Define as estruturas de dados compartilhadas entre os módulos do projeto.
Todos os modelos usam Pydantic v2 para validação e serialização.

Uso:
    from whatsapp_langchain.shared.models import MessageQueue, MessageStatus

    msg = MessageQueue(phone_number="+5511999999999", agent_id="vsa_tech", ...)
"""

from datetime import UTC, date, datetime
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
        description="ID do atendimento associado (None se não houver vinculação).",
    )
    message_id: str | None = None
    phone_number: str = Field(description="Formato E.164, ex: +5511999999999")
    to_number: str | None = None
    agent_id: str = Field(description="Identificador do agente em langgraph.json")
    thread_id: str = Field(description="ID do thread para checkpointer: phone:agent_id")
    incoming_message: str
    # Conexão (cadastrada na UI) que recebeu a mensagem. O worker monta o
    # cliente outbound a partir dela (credenciais do DB) — não há mais
    # instance/número default "via código". None só em rows legadas.
    conexao_id: int | None = None
    # M2.b — provider resolvido via JOIN com `conexao` no claim. None em rows
    # sem conexao_id ou quando a conexão foi removida.
    conexao_provider: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    # Nome do arquivo informado pelo provedor (mig 164). None em row antiga e no
    # Twilio, que não manda nome — aí a extensão é inferida do mime.
    media_filename: str | None = None
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
    """Run enxuta de observabilidade (Langfuse OU LangSmith) pra tabela `/traces`."""

    run_id: str
    name: str | None
    status: str | None
    start_time: str | None
    end_time: str | None
    latency_ms: int | None
    total_tokens: int | None
    thread_id: str | None
    source: str = Field(
        default="langsmith", description="Origem do trace: langfuse | langsmith"
    )
    url: str = Field(default="", description="Deep-link pra UI do provider")
    # Compat retroativa — clientes antigos liam `smith_url`. Espelha `url`.
    smith_url: str = Field(default="", description="Alias legado de `url`")


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
    # Mig 147: avisar o cliente quando um atendente assume (claim). Default
    # False = assume em silêncio, que é o modelo co-piloto (a IA responde e o
    # operador entra e sai). True faz sentido em fila clássica, onde o cliente
    # esperava e passa a falar com uma pessoa.
    anuncia_atendente_assumiu: bool = False
    # Sprint 8 padrão profissional (mig 060)
    menu_coleta_id: int | None = None
    hook_id: int | None = None
    plano_id: int | None = None
    razao_social: str | None = None
    inscricao_estadual: str | None = None
    endereco_fiscal_cep: str | None = None
    endereco_fiscal_logradouro: str | None = None
    endereco_fiscal_numero: str | None = None
    endereco_fiscal_complemento: str | None = None
    endereco_fiscal_bairro: str | None = None
    endereco_fiscal_cidade: str | None = None
    endereco_fiscal_uf: str | None = None
    # White-label por empresa (mig 115)
    logo_path: str | None = None
    nome_exibicao: str | None = None
    cor_primaria: str | None = None
    cor_secundaria: str | None = None
    # Mig 160: quando alguém clicou em "Pular" no wizard de onboarding.
    # Preenchido faz a raiz "/" ir direto pro painel; None mantém o guiado.
    onboarding_dispensado_at: datetime | None = None


class EmpresaMembro(BaseModel):
    """Associa user (Better Auth) a uma empresa com role.

    `is_default=True` marca a empresa que entra automático na sessão quando
    o user não envia X-Empresa-Id. Roles seguem o convention: admin (full
    control), operator (atendimento), viewer (read-only).

    `email` e `status` são opcionais e populados por `list_members` (JOIN
    com auth.user) pra evitar N+1 na UI.
    """

    empresa_id: int
    user_id: str
    role: str
    is_default: bool
    joined_at: datetime
    email: str | None = None
    status: str | None = None


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
    # Sprint 4 padrão profissional (mig 048)
    tipo_atendimento: str = "ia"  # manual|ia|hibrido
    whatsapp_state: str | None = None
    waba_account_id: str | None = None
    waba_phone_id: str | None = None
    waba_app_id: str | None = None
    waba_account_description: str | None = None
    # Sprint Conexões WABA/Evolution (mig 092)
    connection_state: str = (
        "pending"  # pending|qr_pending|open|connecting|disconnected|error|ready
    )
    state_message: str | None = None
    qr_code: str | None = None  # base64 PNG (Evolution)
    qr_expires_at: datetime | None = None
    ultimo_health_check_at: datetime | None = None
    ultimo_health_check_ok: bool | None = None
    webhook_verify_token: str | None = None  # WABA inbound
    # Anti-ban disparador (mig 126): teto diário + aquecimento
    daily_send_cap: int | None = None  # NULL = sem teto manual
    warmup_started_at: datetime | None = None  # NULL = sem aquecimento
    # Agrupamento de resposta (mig 144): segundos que o agente espera antes de
    # responder mensagens seguidas do mesmo contato. 0 desliga.
    resposta_agrupamento_segundos: int = 8
    # Mig 169 — transcreve todo áudio recebido, mesmo sem agente responder.
    transcrever_audio_sempre: bool = False


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
    tipo_atendimento: str | None = None


class ConexaoPatchInput(BaseModel):
    """Payload do PATCH /api/conexoes/{id} — campos editáveis após criação."""

    display_name: str | None = None
    default_agent_id: str | None = None
    is_default: bool | None = None
    tipo_atendimento: str | None = None
    status: str | None = None  # active|disabled (não permite 'error')
    # Anti-ban (mig 126): teto diário de envios + modo aquecimento
    daily_send_cap: int | None = None
    warmup_enabled: bool | None = None  # True liga aquecimento (seta warmup_started_at)
    # Agrupamento de resposta (mig 144). 0 desliga; faixa 0..60 (CHECK no banco)
    resposta_agrupamento_segundos: int | None = Field(default=None, ge=0, le=60)
    transcrever_audio_sempre: bool | None = None


# --- M3 CRM Light: Cliente + Atendimento ---


class Cliente(BaseModel):
    """Pessoa cadastrada na empresa (1 row por empresa+telefone).

    Schema expandido na Fase 1.A enterprise (mig 038): PF/PJ + endereço
    estruturado + lifecycle/score + social + responsável. Todos os campos
    novos são opcionais — webhook continua criando cliente só com telefone.
    """

    id: int
    empresa_id: int
    telefone: str
    nome: str | None = None
    email: str | None = None
    doc: str | None = None  # Legacy — mantido pra compat; novos: cpf/cnpj
    status: str = "active"
    config: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)

    # ---- Fase 1.A: PF/PJ ----
    tipo_pessoa: str | None = None  # 'PF' | 'PJ' | None
    cpf: str | None = None  # só dígitos (11)
    cnpj: str | None = None  # só dígitos (14)
    rg: str | None = None
    razao_social: str | None = None
    nome_fantasia: str | None = None
    data_nascimento: date | None = None
    genero: str | None = None

    # ---- Endereço estruturado ----
    cep: str | None = None  # só dígitos (8)
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None  # 2 chars
    pais: str = "BR"

    # ---- Comercial / lifecycle ----
    segmento: str | None = None
    lifecycle_stage: str | None = (
        None  # lead|qualified|opportunity|customer|evangelist|churned
    )
    score: int | None = None  # 0-100
    source: str | None = None  # whatsapp|website|indicacao|...
    responsavel_user_id: str | None = None
    valor_estimado_brl: float | None = None

    # ---- Social / canais alternativos ----
    instagram: str | None = None
    linkedin: str | None = None
    facebook: str | None = None
    website: str | None = None
    email_alternativo: str | None = None
    telefone_alternativo: str | None = None

    # ---- Localização ----
    locale: str = "pt-BR"
    timezone: str = "America/Sao_Paulo"
    avatar_url: str | None = None

    # ---- Tracking ----
    last_interaction_at: datetime | None = None
    notes: str | None = None

    # ---- Sub-fase B+ (padrão profissional) (mig 046) ----
    whatsapp_state: str | None = None
    numero_verificado: bool = False
    whatsapp_lid: str | None = None
    remote_id: str | None = None
    msg_apos_encerramento: str | None = None
    field_1: str | None = None
    field_2: str | None = None
    field_3: str | None = None
    field_4: str | None = None
    field_5: str | None = None
    ignora_inatividade: bool = False
    desconsidera_turno: bool = False


class ClienteAnotacao(BaseModel):
    id: int
    cliente_id: int
    user_id: str
    conteudo: str
    created_at: datetime


class AgendamentoRegras(BaseModel):
    """Regras de negócio por empresa pra agendamento (S3 Calendar v2).

    Single row por empresa. Defaults: janela 08-18, seg-sex, antecedência
    60min. `dias_semana_permitidos` usa ISO weekday (1=seg, 7=dom).
    `dias_bloqueados` é lista de strings YYYY-MM-DD.
    """

    empresa_id: int
    hora_inicio: str  # "HH:MM" formato (psycopg pode trazer time obj — converter)
    hora_fim: str
    antecedencia_minima_minutos: int = 60
    intervalo_entre_minutos: int = 0
    dias_semana_permitidos: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    dias_bloqueados: list[str] = Field(default_factory=list)
    requer_aprovacao: bool = False
    created_at: datetime
    updated_at: datetime


class AgendamentoRegrasInput(BaseModel):
    """Payload de PUT /api/calendar/regras."""

    hora_inicio: str | None = None
    hora_fim: str | None = None
    antecedencia_minima_minutos: int | None = Field(default=None, ge=0)
    intervalo_entre_minutos: int | None = Field(default=None, ge=0)
    dias_semana_permitidos: list[int] | None = None
    dias_bloqueados: list[str] | None = None
    requer_aprovacao: bool | None = None


class Agendamento(BaseModel):
    """Agendamento espelhado do Google Calendar com governança local (S2).

    `evento_id_externo` é populado após o INSERT no Google. Pode ser NULL
    transitoriamente (se Google falhar, o row local fica como `cancelado`).
    """

    id: int
    empresa_id: int
    calendar_id: str
    user_id_criador: str | None = None
    cliente_id: int | None = None
    evento_id_externo: str | None = None
    summary: str
    descricao: str | None = None
    data_inicio: datetime
    data_fim: datetime
    status: str = "confirmado"
    aprovado: bool = True
    gestor_notificado: bool = False
    payload_externo: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


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
    # S4: telefone E.164 do gestor que recebe pedidos de aprovação via
    # WhatsApp. NULL = sem fluxo de aprovação ativo (mesmo se
    # agendamento_regras.requer_aprovacao=true).
    aprovador_telefone: str | None = None


class CalendarConfigPublic(BaseModel):
    """Versão segura pra UI — sem expor o token bruto."""

    empresa_id: int
    google_email: str | None
    calendar_id: str
    timezone: str
    ativo: bool
    aprovador_telefone: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarConfigInput(BaseModel):
    """Payload pra PUT /api/google-calendar/config (S4 UI)."""

    aprovador_telefone: str | None = None


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
    conexao_id: int | None = None  # mig 129: SET NULL ao apagar a conexão
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
    # Snapshot do canal (mig 129) — gravado na abertura; sobrevive ao apagar a
    # conexão. Reads preferem o dado vivo (JOIN) e caem nestes quando NULL.
    conexao_nome: str | None = None
    conexao_numero: str | None = None
    conexao_provider: str | None = None
    # Sprint 3 padrão profissional (mig 047)
    protocolo: str | None = None
    qtde_resposta_invalida: int = 0
    iniciado_cliente: bool = True
    finalizado_por_user_id: str | None = None
    solicitou_encerramento: bool = False
    # Triagem omnichannel (mig 061): preenchido pelo agente IA via tools
    # `classificar_atendimento` e `transfer_to_human`. Atendente humano
    # vê esses campos no Card "Triagem IA" do drawer.
    departamento_id: int | None = None
    classificacao: str | None = None
    prioridade: str | None = None  # baixa|media|alta|urgente
    sentimento: str | None = None  # positivo|neutro|negativo|frustrado
    resumo_ia: str | None = None
    triagem_completa: bool = False
    triagem_at: datetime | None = None
    # Wizard de coleta multi-pergunta (mig 081/082)
    # `coleta_estado`: runtime do wizard em andamento ({item_id, idx,
    # respostas, perguntas, started_at}). NULL = sem wizard.
    # `coleta_resumo`: snapshot final ({item_id, item_label, respostas:
    # {save_as: {label, valor}}, completed_at}). Exibido no drawer.
    coleta_estado: dict | None = None
    coleta_resumo: dict | None = None
    # Tags aplicadas no atendimento (mig 086). Preenchido pelo loader quando
    # solicitado via `with_tags=True` — evita N+1 no list.
    tags: list[dict] | None = None
    # Estado da pesquisa de satisfação (mig 073). Não é usado pelo drawer — o
    # gate de agrupamento (mig 144) lê estes campos pra saber que o bot está
    # esperando uma nota/comentário e não deve alongar a janela de resposta.
    aguardando_avaliacao_at: datetime | None = None
    aguardando_comentario_at: datetime | None = None
    # --- Campos DERIVADOS (não existem no banco) ---
    # Preenchidos por `list_atendimentos`; ver `derivar_situacao`.
    #
    # `situacao` é o que a UI mostra. Existe para as três interfaces (web, app e
    # o que vier) lerem UM campo em vez de cada uma reimplementar a regra: até
    # aqui `STATUS_LABEL` estava triplicado e já havia divergido — o web dizia
    # "Em andamento" e o app "Em atendimento" para o mesmo estado.
    situacao: str = "com_ia"
    # Tags do CLIENTE (não do atendimento). Identificam a PESSOA — instituição,
    # turma, vínculo — e são o que alimenta as abas. Tag do atendimento vale só
    # para aquela conversa; esta segue o cliente.
    cliente_tags: list[str] = Field(default_factory=list)
    # A IA vai responder a próxima mensagem deste cliente? Eixo separado de
    # propósito, como o `isAiEnabled` do Chatvolt: combinações novas de estado
    # não exigem rótulo novo.
    ia_ativa: bool = True
    # Mensagens do cliente após a última vez que ESTE usuário abriu a conversa.
    # 0 quando não há usuário no contexto (ex.: chamada por service token).
    nao_lidas: int = 0


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
    pasta_id: int | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    # Quantos chunks COM vetor o documento tem. É o que decide se ele existe
    # pro agente: a busca é `documento_conhecimento_chunk` com
    # `d.ativo AND c.embedding IS NOT NULL`. Zero = cadastrado e invisível.
    # Só a listagem preenche; os outros caminhos deixam no default.
    chunks_count: int = 0


class DocumentoConhecimentoInput(BaseModel):
    """Payload do POST/PUT /api/empresas/{id}/base-conhecimento."""

    titulo: str = Field(min_length=1, max_length=200)
    conteudo: str = Field(
        min_length=1, max_length=200000
    )  # sobe de 20k pra 200k pós-chunking
    tags: list[str] = Field(default_factory=list)
    ativo: bool = True
    pasta_id: int | None = None


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
    """Categorização opcional de atendimento (suporte, vendas, etc) — M6.a.

    `parent_id` adicionado em E2.B pra hierarquia em árvore. NULL = root.
    `users_count` é populado quando o handler explicita o JOIN.
    """

    id: int
    empresa_id: int
    nome: str
    descricao: str | None = None
    ativo: bool = True
    parent_id: int | None = None
    users_count: int | None = None
    # Mig 166 — a IA segue respondendo enquanto o atendimento espera na fila.
    # Serve a operação em que a fila é caixa de entrada de uma pessoa só, que
    # lê quando pode; sem isso, o cliente fica sem resposta até alguém puxar.
    ia_continua_na_fila: bool = False
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    # Sprint 4 padrão profissional (mig 049)
    turno_id: int | None = None
    posicao_fila_transferencia: int | None = None
    encerra_atendimento: bool = False
    tolerancia_atend_inativo_min: int | None = None
    enviar_fila_atendimento: bool = False
    menu_coleta_id: int | None = None
    retencao_msg_dias: int | None = None


class DepartamentoInput(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    descricao: str | None = Field(default=None, max_length=200)
    ativo: bool = True
    parent_id: int | None = None
    ia_continua_na_fila: bool = False


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
