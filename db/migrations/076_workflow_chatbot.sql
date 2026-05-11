-- Sprint Workflow-LangGraph PoC — sistema de workflows declarativos
-- que reusam LangGraph StateGraph + AsyncPostgresSaver pra fluxos
-- ZigChat-style com state machine, interrupt() e checkpointing.
--
-- Branch: proposta/menu-langgraph-workflows (NÃO mergea em master sem
-- PoC validado).

CREATE TABLE IF NOT EXISTS workflow_chatbot (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    -- Definição mutável (draft). Cada publicação clona pra workflow_chatbot_version.
    definicao JSONB NOT NULL,
    versao INT NOT NULL DEFAULT 1,
    versao_ativa_id BIGINT,  -- FK pra workflow_chatbot_version (preenchido após mig 077)
    ativo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (empresa_id, slug)
);

-- Apenas um workflow "principal" ativo por empresa (entry point).
-- Subworkflows referenciados por `wf:xxx` podem coexistir com ativo=false.
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_principal_ativo
    ON workflow_chatbot (empresa_id) WHERE ativo AND slug = 'menu_principal';

CREATE INDEX IF NOT EXISTS idx_workflow_empresa_slug
    ON workflow_chatbot (empresa_id, slug);
