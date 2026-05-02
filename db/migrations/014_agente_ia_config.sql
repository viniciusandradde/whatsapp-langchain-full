-- M5.b AgenteIA configurável: admin edita prompt + temperatura sem código.
-- PK composta (empresa_id, agent_id) — cada empresa pode ter suas próprias
-- instruções pro mesmo agente do catálogo (vsa_tech, etc).

CREATE TABLE IF NOT EXISTS agente_ia_config (
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    -- Quando ativo=true e o texto está preenchido, o loader usa este
    -- prompt em vez do SYSTEM_PROMPT do catálogo. NULL/empty = fallback.
    system_prompt_override TEXT,
    -- 0.0..2.0 — repassado direto pro create_chat_model. NULL = default.
    temperatura NUMERIC(3, 2) CHECK (
        temperatura IS NULL OR (temperatura >= 0 AND temperatura <= 2)
    ),
    -- Liga/desliga sem perder o texto (admin pode testar/voltar).
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (empresa_id, agent_id)
);
