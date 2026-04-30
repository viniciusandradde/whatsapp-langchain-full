-- conexao: representa uma linha WhatsApp (Twilio sandbox/prod, WABA, etc)
-- vinculada a uma empresa. O webhook resolve empresa_id + agent_id por
-- lookup no `from_number` (campo `To` do Twilio).
CREATE TABLE IF NOT EXISTS conexao (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    provider TEXT NOT NULL
        CHECK (provider IN ('twilio_sandbox', 'twilio_prod', 'waba')),
    sid TEXT,
    from_number TEXT NOT NULL,
    display_name TEXT,
    default_agent_id TEXT NOT NULL DEFAULT 'vsa_tech',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled', 'error')),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Lookup do webhook é por from_number — cada número em 1 conexão.
    UNIQUE (from_number)
);

CREATE INDEX IF NOT EXISTS idx_conexao_empresa
    ON conexao (empresa_id, status);

-- conexao_id em message_queue: nullable (rows antigas ficam NULL,
-- novas vindas do webhook são atribuídas pela conexão resolvida).
ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS conexao_id BIGINT
    REFERENCES conexao(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_message_queue_conexao
    ON message_queue (conexao_id, status);

-- Bootstrap: cria 1 conexão default pra empresa 1 (VSA Tech) com o número
-- Twilio Sandbox global. Admin pode editar pelo painel após o deploy se
-- usar número diferente (TWILIO_FROM_NUMBER do .env).
INSERT INTO conexao (
    empresa_id, provider, from_number, display_name, default_agent_id,
    is_default, payload_json
) VALUES (
    1, 'twilio_sandbox', '+14155238886', 'Sandbox VSA Tech', 'vsa_tech',
    TRUE, jsonb_build_object('bootstrap', TRUE)
) ON CONFLICT (from_number) DO NOTHING;
