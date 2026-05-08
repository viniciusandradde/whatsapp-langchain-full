-- Sprint M.7 — log de queries RAG pra dashboard de qualidade.
-- Cada chamada da tool `search_knowledge_base` registra:
-- - empresa + query truncada (200 chars)
-- - pasta_ids consultadas (filtro setor)
-- - hits + top_score + duração ms
-- - quem chamou (agente_slug, atendimento_id) pra correlacionar com falhas
--
-- Best-effort: falha de insert NÃO derruba a tool (try/except no caller).

CREATE TABLE rag_query_log (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    pasta_ids BIGINT[] NOT NULL DEFAULT '{}',
    agente_slug TEXT,
    atendimento_id BIGINT,
    thread_id TEXT,
    hits INT NOT NULL DEFAULT 0,
    top_score NUMERIC(5,4),
    duracao_ms INT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rag_query_log_empresa_created
    ON rag_query_log (empresa_id, created_at DESC);

CREATE INDEX idx_rag_query_log_agente_created
    ON rag_query_log (empresa_id, agente_slug, created_at DESC)
    WHERE agente_slug IS NOT NULL;

CREATE INDEX idx_rag_query_log_misses
    ON rag_query_log (empresa_id, created_at DESC)
    WHERE hits = 0;
