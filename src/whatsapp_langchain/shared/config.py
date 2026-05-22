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

    # Sprint A.2.6 — URL para conectar como chat_nexus_app (NOBYPASSRLS).
    # Quando setado, get_pool() retorna pool com essa URL em vez de
    # `database_url` (que continua usado por run_migrations + bootstrap
    # que precisam de superuser / bypass natural).
    # Em prod, idealmente:
    #   DATABASE_URL=postgres (superuser, só pra migs)
    #   DATABASE_URL_APP=chat_nexus_app (NOBYPASSRLS, runtime)
    # Quando vazio (default), app continua usando database_url (modo
    # legacy — RLS inerte pois superuser bypassa).
    database_url_app: str = ""

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
    # Histórico:
    #  - 60: inicial. Estourava reload comum.
    #  - 180 (3 req/s): pages com Promise.all de 4-5 fetches caíam.
    #  - 600 (10 req/s): sprint Atendimento UX adicionou sidebar com
    #    contadores 30s + drawer com SSE fallback polling 5s + tag-popover
    #    + painel-cliente lazy. Burst típico abrir atendimento ~12 reqs.
    # Migration 022_rate_limit_generic.sql precisa estar aplicada.
    admin_rate_limit_per_minute: int = 600

    # --- Sprint L — Test Runner UI ---
    # Quando True, expõe `/api/admin/tests/*` endpoints + UI `/relatorios/allure`.
    # Default False: feature opt-in (requer Java + allure CLI + dev deps no
    # container API). Em prod set ENABLE_TEST_RUNNER=true via env.
    enable_test_runner: bool = False

    # --- Sprint Workflow-LangGraph (proposta/menu-langgraph-workflows) ---
    # Quando True, worker tenta `workflows.runner.process()` antes de cair
    # no `_try_handle_menu` legacy. Feature flag por empresa via
    # `workflow_chatbot.ativo` — desabilitada empresa-por-empresa fica no menu_item.
    # Default False: feature opt-in, evita regressão em prod.
    enable_workflow_engine: bool = False

    # --- Sprint Wareline ConecteHub (integrações externas multi-tenant) ---
    # Chave Fernet (base64 urlsafe 32 bytes) usada pra cifrar credenciais
    # Wareline (password + client_secret) na tabela `wareline_credentials`.
    # Gerar: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Sem essa chave, integração Wareline (e qualquer outra integração que use
    # `integrations.crypto`) fica desabilitada (rotas retornam 503).
    wareline_encryption_key: SecretStr | None = None

    # --- Sprint Conexões — WhatsApp Cloud API (Meta WABA Embedded Signup) ---
    # App registrado em developers.facebook.com com produto "WhatsApp Business Platform"
    # e Embedded Signup habilitado. configuration_id é gerado lá.
    # Sem essas vars, rotas /api/conexoes/waba/* respondem 503 e card WABA em UI
    # mostra mensagem "Meta App não configurado".
    meta_app_id: str = ""
    meta_app_secret: SecretStr | None = None
    meta_config_id: str = ""
    # Default vazio → calculado em runtime baseado no public_base_url (se setado).
    meta_oauth_redirect_uri: str = ""
    # Token único pra validar handshake GET /webhook/waba (hub.verify_token).
    # Gerar uuid4 e setar UMA VEZ. Reutilizado por todas as conexões WABA.
    waba_webhook_verify_token: SecretStr | None = None
    # Versão Graph API (atualizar periodicamente — Meta deprecia ~1x/ano).
    waba_graph_api_version: str = "v21.0"

    # --- Sprint Conexões — Evolution admin (auto-provision de instances) ---
    # URL do Evolution server pra ops admin (create/connect/disconnect instance).
    # Por default usa evolution_api_url se vazio.
    evolution_admin_url: str = ""
    # api-key GLOBAL do Evolution (header `apikey` requerido pra rotas /instance/*).
    # Diferente de evolution_api_key (que é per-instance).
    evolution_global_api_key: SecretStr | None = None

    # Base URL pública do app (usado pra montar redirect URIs de OAuth + webhook URLs
    # nas integrações WABA/Evolution quando user não setou explicitamente).
    # Ex: https://chat.vsanexus.com (sem barra final).
    public_base_url: str = ""

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
    def resolved_meta_oauth_redirect_uri(self) -> str:
        """Redirect URI do OAuth Meta — usa override se setado, senão public_base_url."""
        explicit = self.meta_oauth_redirect_uri.strip()
        if explicit:
            return explicit
        base = self.public_base_url.strip().rstrip("/")
        if base:
            return f"{base}/api/conexoes/waba/oauth/callback"
        return "http://localhost:8000/api/conexoes/waba/oauth/callback"

    @property
    def resolved_evolution_admin_url(self) -> str:
        """URL admin do Evolution — fallback pra evolution_api_url se vazio."""
        return (self.evolution_admin_url or self.evolution_api_url).strip()

    @property
    def waba_enabled(self) -> bool:
        """True quando as 4 env vars mínimas pra WABA estão setadas."""
        return bool(
            self.meta_app_id
            and self.meta_app_secret
            and self.meta_config_id
            and self.waba_webhook_verify_token
        )

    @property
    def resolved_evolution_global_api_key(self) -> SecretStr | None:
        """Fallback: usa EVOLUTION_API_KEY se EVOLUTION_GLOBAL_API_KEY não setada.

        Em deploys single-instance comuns o user só tem uma key — a mesma serve
        pra outbound de mensagens e pra ops admin (create/delete instance).
        """
        return self.evolution_global_api_key or self.evolution_api_key

    @property
    def evolution_admin_enabled(self) -> bool:
        """True quando há URL admin + alguma api-key (global ou normal)."""
        return bool(
            self.resolved_evolution_admin_url
            and self.resolved_evolution_global_api_key
        )

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
        """Valida configuração mínima e hardening por ambiente.

        Em produção, aplica hardening de Sprint D (2026-05-22):
        - Twilio: se `TWILIO_OUTBOUND_MODE=real`, signature validation
          OBRIGATÓRIA (raise). Webhook sem HMAC = forgery trivial.
        - Evolution: se `EVOLUTION_OUTBOUND_MODE=real`, apikey validation
          OBRIGATÓRIA (raise). Webhook sem apikey = forgery trivial.
        - WABA: se `META_APP_SECRET` configurado, fica documentado que
          signature é enforced em runtime (`webhook_waba.py`).

        Não-prod (dev/test): apenas warnings, sem bloquear.
        """
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

        if self.is_production and not self.frontend_origins_list:
            raise ValueError(
                "Production requer FRONTEND_ORIGINS configurado com pelo menos uma "
                "origem. Ex: FRONTEND_ORIGINS=https://chat.vsanexus.com"
            )

        # Sprint D hardening — webhook signature obrigatória se provider real
        twilio_mode = self.resolved_twilio_outbound_mode
        if (
            self.is_production
            and twilio_mode == "real"
            and not self.validate_twilio_signature
        ):
            raise ValueError(
                "Production com TWILIO_OUTBOUND_MODE=real exige "
                "VALIDATE_TWILIO_SIGNATURE=true. Endpoint /webhook/twilio sem "
                "HMAC aceita qualquer payload forjado — risco de account "
                "takeover via mensagens falsas."
            )

        if (
            self.is_production
            and self.evolution_outbound_mode.strip().lower() == "real"
            and not self.evolution_validate_apikey
        ):
            raise ValueError(
                "Production com EVOLUTION_OUTBOUND_MODE=real exige "
                "EVOLUTION_VALIDATE_APIKEY=true. Endpoint /webhook/evolution "
                "sem validação de apikey aceita qualquer payload forjado."
            )


# Singleton — importar de qualquer lugar do projeto
settings = Settings()
