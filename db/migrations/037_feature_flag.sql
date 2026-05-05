-- Fase 0.2: Feature flags por empresa.
--
-- Permite ativar/desativar features experimentais por tenant sem
-- redeploy. Casos de uso:
--   - Beta testing: cliente X ganha "novo dashboard" antes do rollout geral
--   - Killswitch: desabilitar feature problemática num tenant sem afetar outros
--   - A/B test: split entre `value=true` e `value=false`
--
-- value JSONB pra suportar flags não-booleanas (ex: {"variant": "A", "limit": 50}).
-- Pra consulta booleana simples, usar value = 'true'::jsonb.

CREATE TABLE IF NOT EXISTS feature_flag (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    key TEXT NOT NULL,                          -- ex: 'new_dashboard', 'mcp_beta', 'auto_routing'
    value JSONB NOT NULL DEFAULT 'true'::jsonb,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,        -- soft-disable sem deletar (preserva audit)
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, key)
);

CREATE INDEX IF NOT EXISTS idx_feature_flag_empresa
    ON feature_flag (empresa_id) WHERE ativo;
