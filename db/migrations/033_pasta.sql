-- E2.C M7: organização hierárquica da base de conhecimento.
--
-- Pasta é puramente uma container — filtra a busca/UI sem afetar
-- o ranking. Nome único por (empresa_id, parent_id) — duas pastas
-- "FAQ" só podem existir se estiverem em árvores diferentes.
--
-- Documentos sem pasta_id ficam na "raiz" (NULL). Operação SET NULL
-- na FK preserva docs órfãos quando a pasta é deletada.

CREATE TABLE IF NOT EXISTS pasta (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    parent_id BIGINT REFERENCES pasta(id) ON DELETE SET NULL,
    descricao TEXT,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- UNIQUE (empresa_id, parent_id, nome) com NULLS NOT DISTINCT pra
-- bloquear duplicatas em raiz (PostgreSQL 15+). Em versões mais antigas,
-- caímos no índice parcial abaixo como workaround.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pasta_empresa_parent_nome
    ON pasta (empresa_id, COALESCE(parent_id, 0), nome);

CREATE INDEX IF NOT EXISTS idx_pasta_empresa_parent
    ON pasta (empresa_id, parent_id);


ALTER TABLE documento_conhecimento
    ADD COLUMN IF NOT EXISTS pasta_id BIGINT
        REFERENCES pasta(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documento_pasta
    ON documento_conhecimento (pasta_id) WHERE pasta_id IS NOT NULL;
