-- Sprint Conexões: WhatsApp Oficial (WABA OAuth Embedded Signup) + Evolution auto-provision.
--
-- 1. Credenciais cifradas (Fernet) — WABA access_token (System User) ou Evolution api_key
--    armazenadas em credentials_encrypted (substitui payload_json pra campos sensíveis).
-- 2. State machine de conexão (pending → qr_pending → open/ready → disconnected/error)
--    pra UI mostrar badge colorido + polling de QR Evolution funcionar.
-- 3. webhook_verify_token: token gerado pra cada conexão WABA, usado pra validar handshake
--    Meta no GET /webhook/waba (`hub.verify_token`).
-- 4. qr_code + qr_expires_at: Evolution retorna QR base64 com TTL ~45s; armazenamos pra
--    front re-renderizar sem nova call ao Evolution server enquanto ainda válido.
-- 5. Fix do gap: hoje UNIQUE(from_number) bloqueia 2 empresas com mesmo número (acontece
--    em sandbox Twilio compartilhado). Troca pra UNIQUE(empresa_id, from_number).
-- 6. Index waba_phone_id: webhook Meta resolve conexão por phone_number_id do payload —
--    índice parcial só pra rows WABA.

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS credentials_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS webhook_verify_token TEXT,
    ADD COLUMN IF NOT EXISTS connection_state TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS state_message TEXT,
    ADD COLUMN IF NOT EXISTS qr_code TEXT,
    ADD COLUMN IF NOT EXISTS qr_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ultimo_health_check_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ultimo_health_check_ok BOOLEAN;

-- CHECK em separado (ADD COLUMN com CHECK + IF NOT EXISTS dá problema em Postgres antigo)
ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_connection_state_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_connection_state_check
    CHECK (connection_state IN (
        'pending', 'qr_pending', 'open', 'connecting',
        'disconnected', 'error', 'ready'
    ));

-- Fix UNIQUE: número único POR EMPRESA, não global.
-- (rows antigas podem ter from_number duplicado entre empresas; índice CONCURRENTLY não
--  funciona dentro de transação então só usa CREATE UNIQUE INDEX normal — assume DBA
--  resolveu duplicatas antes de aplicar, ou que não há nenhuma em prod ainda.)
ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_from_number_key;
DROP INDEX IF EXISTS conexao_from_number_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_conexao_empresa_from_number
    ON conexao (empresa_id, from_number);

-- Webhook WABA lookup por phone_number_id (só pra rows com waba_phone_id setado)
CREATE INDEX IF NOT EXISTS idx_conexao_waba_phone_id
    ON conexao (waba_phone_id)
    WHERE waba_phone_id IS NOT NULL;

-- Cache de state CSRF do OAuth Meta (Embedded Signup). State vive 10min.
-- Linkado a empresa_id + user_id pra debug + segurança. Cleanup via TTL.
CREATE TABLE IF NOT EXISTS waba_oauth_state (
    state TEXT PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    display_name TEXT,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waba_oauth_state_expires
    ON waba_oauth_state (expires_at);
