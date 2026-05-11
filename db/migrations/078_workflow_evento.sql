-- Sprint Workflow-LangGraph MVP — audit log de transições do workflow.
--
-- Usado pra:
-- 1. LGPD compliance (registro do "lgpd_consented" event obrigatório)
-- 2. Debug L2 ("travou na pergunta de CPF do atendimento 1234")
-- 3. Analytics futuros (drop-off rate por node)
--
-- 1 row por evento. Não substituí o checkpoint LangGraph — complementa.

CREATE TABLE IF NOT EXISTS workflow_evento (
    id BIGSERIAL PRIMARY KEY,
    workflow_version_id BIGINT
        REFERENCES workflow_chatbot_version(id) ON DELETE SET NULL,
    atendimento_id BIGINT NOT NULL,
    empresa_id BIGINT NOT NULL,
    node_id TEXT NOT NULL,
    evento TEXT NOT NULL CHECK (evento IN (
        'entered',
        'exited',
        'interrupt_emitted',
        'resumed',
        'var_saved',
        'validation_failed',
        'handover',
        'delegate_agent',
        'lgpd_consented',
        'error'
    )),
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wf_evento_atend
    ON workflow_evento (atendimento_id, created_at);

-- Index parcial pra queries de compliance LGPD (auditoria)
CREATE INDEX IF NOT EXISTS idx_wf_evento_lgpd
    ON workflow_evento (workflow_version_id, evento)
    WHERE evento = 'lgpd_consented';
