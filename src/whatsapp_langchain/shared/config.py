"""Configuração centralizada via variáveis de ambiente.

Usa pydantic-settings para carregar, validar e tipar todas as configurações
do projeto a partir de variáveis de ambiente ou arquivo .env.

Uso:
    from whatsapp_langchain.shared.config import settings

    print(settings.database_url)
    print(settings.rate_limit_per_hour)

A maior parte das configurações tem defaults sensatos para desenvolvimento local.
Segredos compartilhados do painel/admin devem ser preenchidos explicitamente.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Configurações do projeto carregadas de variáveis de ambiente.

    Cada campo corresponde a uma env var (case-insensitive).
    Ex: database_url → DATABASE_URL
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = (
        "postgresql://postgres:postgres@localhost:5432/whatsapp_langchain"
    )

    # --- Environment ---
    # "development" (default) ou "production" — controla comportamentos como
    # exposicao do webhook sincrono (desabilitado em production)
    environment: str = "development"

    # --- Server ---
    port: int = 8000
    log_level: str = "info"
    log_json: bool = False  # True em prod para logs estruturados

    # --- Twilio ---
    # Inbound (validação de assinatura no webhook)
    validate_twilio_signature: bool = False
    twilio_auth_token: str = ""
    twilio_webhook_url: str = ""

    # Outbound (envio de mensagens pelo worker via API Key)
    # Em dev local o fallback efetivo e "mock"; em production, "real".
    twilio_outbound_mode: str = ""
    twilio_account_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    twilio_from_number: str = ""

    # --- Twilio Live Tests (smoke pré-deploy) ---
    # CUIDADO: rodar só manualmente. Cada teste envia mensagem real e cobra crédito.
    twilio_live_tests: bool = False
    twilio_test_to_number: str = ""

    # --- Google Calendar (M5.a) ---
    # OAuth Web Application credentials (Google Cloud Console).
    # Vazio desativa a integração — endpoints respondem 503 e tools do
    # agente não são injetadas.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr | None = None
    # Redirect que o Google bate de volta após o user autorizar. Tem que
    # coincidir EXATAMENTE com a URI cadastrada no console do Google.
    # Em prod: https://chat.nexus.hospitalevangelico.com.br/api/google-calendar/oauth/callback
    google_oauth_redirect_uri: str = (
        "http://localhost:8081/api/google-calendar/oauth/callback"
    )

    # --- Rate Limit (webhook inbound por phone_number, sliding window 1h) ---
    # Default subido de 30 → 120 (2 msg/min sustentado) porque cliente real
    # facilmente excede 30 em sessão de teste/atendimento longo + retries de
    # mídia do Evolution (cada upload audio/imagem retenta múltiplas vezes
    # se o INSERT na fila falha).
    rate_limit_per_hour: int = 120
    # True ativa Postgres sliding window (necessário em multi-instância).
    # Migration 005_rate_limit_buckets.sql precisa estar aplicada.
    rate_limit_distributed: bool = False

    # Rate limit pra endpoints admin (/api/*) por user_id.
    # Generoso pra UX normal, bloqueia scraping/abuso por sessão comprometida.
    # Default subido pra 180 (3 req/s sliding) porque pages do painel
    # disparam múltiplas chamadas em paralelo por load (Promise.all com
    # 4-5 fetches) e reload do admin estourava facilmente o antigo 60.
    # Migration 022_rate_limit_generic.sql precisa estar aplicada.
    admin_rate_limit_per_minute: int = 180

    # --- Debounce ---
    message_buffer_seconds: float = 2.0

    # --- LLM (OpenRouter) ---
    # Todas as chamadas LLM, embeddings e transcrição usam OpenRouter
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "x-ai/grok-4.1-fast"
    # Modelo dedicado ao pré-processamento de mídia (imagem/áudio)
    openrouter_midia_model: str = "google/gemini-2.5-flash-lite"

    # --- LLM Rate Limit ---
    llm_rate_limit_requests_per_second: float = 0.5
    llm_rate_limit_max_burst: int = 10

    # --- Worker ---
    poll_interval_seconds: float = 1.0
    lease_seconds: int = 60
    max_attempts: int = 3

    # --- Media ---
    media_image_enabled: bool = True
    media_audio_enabled: bool = True
    media_document_enabled: bool = True

    # --- Context Management (migrado do .env manual) ---
    context_strategy: str = "trim"
    trim_keep_turns: int = 5
    summarize_trigger_tokens: int = 4000
    summarize_keep_messages: int = 10
    summarize_model: str = "x-ai/grok-4.1-fast"

    # --- Internal Service Token ---
    # Token compartilhado entre frontend e API para proteger rotas administrativas.
    # Preencha também em desenvolvimento; em produção, use um token forte.
    internal_service_token: str = ""

    # --- CORS / Security Headers ---
    # Lista CSV de origens permitidas para CORS. Em produção, restrinja ao domínio
    # do frontend. Em desenvolvimento, o default permite localhost:3000.
    frontend_origins: str = "http://localhost:3000"

    # --- LangSmith (opcional — só usado pelo /api/traces do painel) ---
    langchain_api_key: SecretStr | None = None
    langchain_project: str = ""

    # --- Semantic Memory (LangGraph Store) ---
    memory_enabled: bool = True
    # Nome do modelo no OpenRouter (sem prefixo "openai:")
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dims: int = 1536
    memory_search_limit: int = 5

    # --- M2.b Evolution API (WhatsApp não-oficial) ---
    # Vazio desativa a integração — endpoints respondem 503 e o worker
    # não inicializa cliente Evolution. Quando preenchido + ao menos
    # uma conexão `provider='evolution'` cadastrada, mensagens fluem
    # pelo pipeline normal.
    evolution_api_url: str = ""
    evolution_api_key: SecretStr | None = None
    # Instance default — só pra teste rápido / pré-cadastro UI. Em
    # produção o instance_name vem da `conexao.payload_json`.
    evolution_instance_name: str = ""
    evolution_phone_number: str = ""
    # mock = log only; real = HTTP de fato. Default safe em dev.
    evolution_outbound_mode: str = "mock"
    # Quando true, valida header `apikey` no /webhook/evolution.
    # Obrigatório true em produção (validate_runtime_settings checa).
    evolution_validate_apikey: bool = False

    @property
    def frontend_origins_list(self) -> list[str]:
        """Retorna a lista de origens CORS a partir do CSV em FRONTEND_ORIGINS."""
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def resolved_twilio_outbound_mode(self) -> str:
        """Resolve o modo outbound do Twilio com fallback seguro por ambiente."""
        mode = self.twilio_outbound_mode.strip().lower()
        if mode:
            return mode

        return "real" if self.environment == "production" else "mock"

    @property
    def is_production(self) -> bool:
        """Indica se a aplicacao esta rodando em modo production."""
        return self.environment.strip().lower() == "production"

    def validate_runtime_settings(self) -> None:
        """Valida configuração mínima e hardening por ambiente."""
        token = self.internal_service_token.strip()
        if not token:
            raise ValueError(
                "INTERNAL_SERVICE_TOKEN deve ser preenchido antes de subir a API."
            )

        if self.is_production and len(token) < MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                "Production requer valor forte para INTERNAL_SERVICE_TOKEN. "
                "Atualize as env vars antes do deploy."
            )

        if self.is_production and not self.validate_twilio_signature:
            raise ValueError(
                "Production requer VALIDATE_TWILIO_SIGNATURE=true. "
                "Sem isso o endpoint /webhook/twilio aceita payloads não autenticados."
            )

        if self.is_production and not self.frontend_origins_list:
            raise ValueError(
                "Production requer FRONTEND_ORIGINS configurado com pelo menos uma "
                "origem. Ex: FRONTEND_ORIGINS=https://chat.nexus.com"
            )


# Singleton — importar de qualquer lugar do projeto
settings = Settings()
