-- M5.c Base de Conhecimento (RAG): cada empresa cadastra FAQs/políticas
-- que o agente pode consultar via tool `search_knowledge_base` antes de
-- responder. Embedding é gerado no upsert e armazenado inline.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documento_conhecimento (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    -- Dimensão fixa em 1536 (text-embedding-3-small). NULL quando o
    -- embedding ainda não foi gerado (ex: provider offline no upsert).
    embedding vector(1536),
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Liga/desliga sem deletar — agente só busca em docs ativos.
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup por empresa (ativos) — usado pelo gate `has_active_documents`
-- no loader e pelo CRUD de listagem.
CREATE INDEX IF NOT EXISTS idx_documento_conhecimento_empresa
    ON documento_conhecimento(empresa_id) WHERE ativo;

-- IVFFlat com cosine similarity. lists=100 funciona bem até ~10k docs;
-- se passar disso, recriar com lists ~ sqrt(rows).
CREATE INDEX IF NOT EXISTS idx_documento_conhecimento_embedding
    ON documento_conhecimento USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
