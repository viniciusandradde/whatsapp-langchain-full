-- Sprint N.5 — adiciona colunas de modo de busca + HyDE no log RAG.
--
-- Permite dashboard agregar por modo (vector|hybrid|hybrid_hyde) e
-- ver qual estratégia funcionou melhor por agente.

ALTER TABLE rag_query_log
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'hybrid',
    ADD COLUMN IF NOT EXISTS hyde_query TEXT;

CREATE INDEX IF NOT EXISTS idx_rag_query_log_mode
    ON rag_query_log (empresa_id, mode, created_at DESC);
