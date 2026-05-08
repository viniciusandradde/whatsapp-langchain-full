-- Sprint O — Guardrails (smart guards condicional).
--
-- 2 tabelas:
-- - guardrail_log: cada vez que um guardrail detecta algo (block/redact/judge)
-- - acao_pendente: HITL — tool que precisa aprovação humana antes de executar

CREATE TABLE guardrail_log (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
    layer TEXT NOT NULL CHECK (layer IN ('input','context','action','output')),
    guardrail TEXT NOT NULL,        -- 'content_filter' | 'pii_redact' | 'hitl' | 'llm_judge'
    decision TEXT NOT NULL,         -- 'allow' | 'block' | 'redact' | 'pending' | 'unsafe'
    pattern_matched TEXT,           -- regex/categoria que casou
    sample TEXT,                    -- trecho do conteúdo (truncado, redacted)
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_guardrail_log_empresa_layer
    ON guardrail_log (empresa_id, layer, created_at DESC);
CREATE INDEX idx_guardrail_log_decision
    ON guardrail_log (empresa_id, decision, created_at DESC)
    WHERE decision IN ('block','unsafe','pending');

-- HITL — ações pendentes de aprovação
CREATE TABLE acao_pendente (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    agente_slug TEXT NOT NULL,
    tool_name TEXT NOT NULL,        -- 'transfer_to_human' | 'cancelar_agendamento' | 'criar_agendamento'
    tool_args JSONB NOT NULL,
    -- justificativa do agente (texto livre)
    motivo TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','expired')) DEFAULT 'pending',
    reviewed_by_user_id TEXT,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    -- TTL: pendentes >24h viram expired (cron futura)
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_acao_pendente_status
    ON acao_pendente (empresa_id, status, created_at DESC);
CREATE INDEX idx_acao_pendente_atendimento
    ON acao_pendente (atendimento_id, created_at DESC);

-- Trigger: notifica via LISTEN/NOTIFY pra SSE
CREATE OR REPLACE FUNCTION notify_acao_pendente_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'acao_pendente_change',
        json_build_object(
            'id', NEW.id,
            'empresa_id', NEW.empresa_id,
            'atendimento_id', NEW.atendimento_id,
            'tool_name', NEW.tool_name,
            'status', NEW.status,
            'op', TG_OP
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS acao_pendente_notify ON acao_pendente;
CREATE TRIGGER acao_pendente_notify
    AFTER INSERT OR UPDATE OF status ON acao_pendente
    FOR EACH ROW EXECUTE FUNCTION notify_acao_pendente_change();
