-- E1.8: histórico de eventos de autenticação (login, logout, reset, etc).
--
-- Persiste cada tentativa de login (sucesso ou falha) + outras ações
-- relevantes (sign-out, password-reset, password-changed) com IP e
-- user-agent. Permite:
-- - Audit de segurança ("quem logou quando?")
-- - Detecção de brute-force (já mitigado pelo rate_limit, mas aqui dá
--   visibilidade)
-- - Compliance ("usuário X acessou em Y data?")
--
-- Retenção 90 dias via cron / cleanup inline (manual por enquanto).

CREATE TABLE IF NOT EXISTS auth_login_event (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    email TEXT,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'login_success',
            'login_failed',
            'logout',
            'password_reset_requested',
            'password_changed',
            'session_blocked_disabled'
        )),
    ip_address TEXT,
    user_agent TEXT,
    reason TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_event_user_created
    ON auth_login_event (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_login_event_email_created
    ON auth_login_event (email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_login_event_created
    ON auth_login_event (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_login_event_type
    ON auth_login_event (event_type, created_at DESC);
