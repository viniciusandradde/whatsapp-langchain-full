-- M5.b.2 Memória estruturada por cliente.
--
-- Diferença em relação a `cliente_anotacao` (M3):
-- - anotacao: livre, escrita por operadores e agente, visível em UI,
--   sem busca semântica.
-- - cliente_memoria: estruturada por categoria, indexada por embedding,
--   buscável semanticamente, focada em fatos que o agente vai recuperar
--   em conversas futuras.
--
-- Categorias:
-- - 'perfil': dados estáveis (estado civil, profissão, contexto de vida)
-- - 'preferencia': gostos/escolhas ("prefere comunicação por email")
-- - 'fato': eventos pontuais ("comprou produto X em janeiro")
--
-- Source:
-- - 'agent_explicit': agente decidiu salvar via tool save_cliente_fato
-- - 'agent_extracted': pipeline background extraiu (futuro M5.b.2.1)
-- - 'operator': operador humano cadastrou via UI (futuro)

CREATE TABLE IF NOT EXISTS cliente_memoria (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    categoria TEXT NOT NULL CHECK (categoria IN ('perfil', 'preferencia', 'fato')),
    conteudo TEXT NOT NULL,
    embedding vector(1536),
    source TEXT NOT NULL DEFAULT 'agent_explicit'
        CHECK (source IN ('agent_explicit', 'agent_extracted', 'operator')),
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup por (empresa, cliente) — usado pra read_cliente_memoria + dedupe.
CREATE INDEX IF NOT EXISTS idx_cliente_memoria_scope
    ON cliente_memoria(empresa_id, cliente_id);

-- IVFFlat cosine pra busca semântica (pgvector já habilitado em M5.c).
CREATE INDEX IF NOT EXISTS idx_cliente_memoria_embedding
    ON cliente_memoria USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Dedup textual exato — se o mesmo conteúdo é cadastrado 2x
-- (mesma empresa, mesmo cliente, mesma categoria), não cria 2 rows.
-- Dedup semântico (similar mas não idêntico) é tratado no helper Python
-- via threshold de cosine similarity.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cliente_memoria_dedup_exato
    ON cliente_memoria(empresa_id, cliente_id, categoria, md5(conteudo));
