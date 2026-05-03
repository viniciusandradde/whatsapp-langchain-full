-- M5.c.1 RAG chunking: 1 doc passa a ter N chunks indexados.
--
-- Antes (M5.c): embedding ficava em `documento_conhecimento.embedding`,
--               1 vetor por doc inteiro — perde precisão em docs longos.
-- Depois (M5.c.1): embedding migra pra `documento_conhecimento_chunk`,
--                  busca cosine acontece em chunks + LLM reranker
--                  retorna top-3 trechos com citação chunk_idx.
--
-- Backfill dos chunks dos docs existentes vem em P4 (script Python).
-- Por enquanto a coluna `embedding` no documento fica como deprecated
-- (será removida quando a migração de dados terminar). NULL nos novos.

CREATE TABLE IF NOT EXISTS documento_conhecimento_chunk (
    id BIGSERIAL PRIMARY KEY,
    documento_id BIGINT NOT NULL REFERENCES documento_conhecimento(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Ordem do chunk dentro do doc (0-indexed) — agente cita
    -- "Doc X, trecho N" ou frontend reconstrói o doc na ordem.
    chunk_idx INTEGER NOT NULL,
    conteudo TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (documento_id, chunk_idx)
);

-- Lookup por empresa pra cosine search (filtra antes do <=>).
CREATE INDEX IF NOT EXISTS idx_chunk_empresa
    ON documento_conhecimento_chunk(empresa_id);

-- IVFFlat cosine — mesmo padrão do M5.c. Lists=100 funciona até ~10k
-- chunks; reindexar com sqrt(N) quando crescer.
CREATE INDEX IF NOT EXISTS idx_chunk_embedding
    ON documento_conhecimento_chunk USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
