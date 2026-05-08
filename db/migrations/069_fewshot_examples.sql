-- Sprint P.3 — exemplos few-shot pra injetar no system prompt.
--
-- Quando atendimento.outcome=success, captura (última pergunta cliente,
-- última resposta agente) como exemplo positivo. Em runtime, busca
-- top-3 mais similares por embedding e injeta no prompt do agente.

CREATE TABLE fewshot_example (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    agente_slug TEXT NOT NULL,
    cliente_msg TEXT NOT NULL,
    agente_resposta TEXT NOT NULL,
    embedding vector(1536),
    -- Sinais de qualidade
    outcome TEXT NOT NULL CHECK (outcome IN ('success','manual_curation')),
    csat_nota INT,
    atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
    -- Status: pending = embeddings ainda não gerados; ready = pronto pra uso
    status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('pending','ready','disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fewshot_empresa_agente
    ON fewshot_example (empresa_id, agente_slug)
    WHERE status = 'ready' AND embedding IS NOT NULL;

CREATE INDEX idx_fewshot_embedding
    ON fewshot_example USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)
    WHERE status = 'ready';
