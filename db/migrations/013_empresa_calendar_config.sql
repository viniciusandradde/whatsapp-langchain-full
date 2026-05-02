-- M5.a Google Calendar: 1 row por empresa com OAuth + calendar default.
-- O agente lê esta tabela (via tool injetada) pra resolver credenciais
-- por empresa antes de chamar Calendar API.

CREATE TABLE IF NOT EXISTS empresa_calendar_config (
    empresa_id BIGINT PRIMARY KEY REFERENCES empresa(id) ON DELETE CASCADE,
    -- credenciais OAuth do Google. Armazenamos o JSON serializado da
    -- google.oauth2.credentials.Credentials (token, refresh_token,
    -- token_uri, client_id, client_secret, scopes, expiry).
    oauth_credentials_json JSONB NOT NULL,
    -- Email da conta Google que autorizou (audit + UI).
    google_email TEXT,
    -- Calendar onde o agente cria/lê eventos. "primary" funciona pra a
    -- maioria; o admin pode trocar pra outro calendário do mesmo dono.
    calendar_id TEXT NOT NULL DEFAULT 'primary',
    -- Timezone usado nos slots e eventos. IANA name (ex: America/Sao_Paulo).
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    -- Liga/desliga sem perder o token (pra debug/manutenção).
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
