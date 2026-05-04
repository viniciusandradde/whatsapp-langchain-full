-- Dead Letter Queue de hooks (E1.4): hooks que falharam após N tentativas
-- (configurável, default 3) caem aqui pra retry manual via UI/API.
--
-- Diferença de hook_log: hook_log persiste TODA tentativa (sucesso ou
-- falha individual). hook_dead_letter persiste só hooks que esgotaram
-- todas tentativas — superfície menor pra operador investigar.
--
-- Status:
-- - 'pending'  → aguarda retry manual (não dispara automaticamente)
-- - 'retrying' → claim em curso (lease via updated_at)
-- - 'done'     → reentregue com sucesso após retry manual
-- - 'archived' → operador marcou como "ignorar"

CREATE TABLE IF NOT EXISTS hook_dead_letter (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    hook_id BIGINT NOT NULL REFERENCES hook(id) ON DELETE CASCADE,
    evento TEXT NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL,
    last_status_code INTEGER,
    last_response_body TEXT,
    last_error TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'retrying', 'done', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_retry_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hook_dead_letter_empresa_status
    ON hook_dead_letter (empresa_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hook_dead_letter_hook
    ON hook_dead_letter (hook_id);
