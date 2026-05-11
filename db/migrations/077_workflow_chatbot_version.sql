-- Sprint Workflow-LangGraph PoC — versões imutáveis do workflow.
--
-- Atendimentos em curso usam `version_id` congelado no WorkflowState
-- pra não quebrar quando admin edita a `definicao` mutável.

CREATE TABLE IF NOT EXISTS workflow_chatbot_version (
    id BIGSERIAL PRIMARY KEY,
    workflow_id BIGINT NOT NULL REFERENCES workflow_chatbot(id) ON DELETE CASCADE,
    versao INT NOT NULL,
    definicao JSONB NOT NULL,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    published_by_user_id TEXT,
    UNIQUE (workflow_id, versao)
);

ALTER TABLE workflow_chatbot
    ADD CONSTRAINT fk_versao_ativa
    FOREIGN KEY (versao_ativa_id) REFERENCES workflow_chatbot_version(id);

CREATE INDEX IF NOT EXISTS idx_workflow_version_workflow
    ON workflow_chatbot_version (workflow_id, versao DESC);
