-- Sprint P.2 — sugestões de docs auto-geradas a partir de queries que
-- falharam (hits=0 ou outcome=transferred/escalated).
--
-- Job nightly clusteriza queries similares e gera draft via LLM. Admin
-- aprova/rejeita pela UI; aprovados viram documento_conhecimento.

CREATE TABLE documento_sugerido (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    pasta_id BIGINT REFERENCES pasta(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL,
    conteudo_draft TEXT NOT NULL,
    -- Queries que originaram a sugestão (sample, max 20)
    queries_amostra TEXT[] NOT NULL DEFAULT '{}',
    -- Quantas queries similares (no cluster)
    cluster_size INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','archived')) DEFAULT 'pending',
    reviewed_by_user_id TEXT,
    reviewed_at TIMESTAMPTZ,
    promoted_doc_id BIGINT REFERENCES documento_conhecimento(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_doc_sugerido_empresa_status
    ON documento_sugerido (empresa_id, status, created_at DESC);
