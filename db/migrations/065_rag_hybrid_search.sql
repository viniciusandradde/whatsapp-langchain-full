-- Sprint N.1 — Busca híbrida (cosine + FTS) com Reciprocal Rank Fusion.
--
-- Antes: search_knowledge_base usa só cosine top-N → erra em queries
-- com termos exatos (códigos, nomes próprios, números).
--
-- Agora: combina:
--   - cosine similarity (semântico)
--   - to_tsvector('portuguese') + ts_rank_cd (lexical/BM25-like)
--   - RRF (Reciprocal Rank Fusion) com K=60 + pesos vector=1.0 / text=1.5
--
-- Inspirado em ai-agent-sales/sql/kb/03_functions.sql:69-144.

-- 1. Coluna FTS — gerada (computed) pra ficar sempre em sync com conteudo
ALTER TABLE documento_conhecimento_chunk
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese', coalesce(conteudo, ''))) STORED;

-- 2. GIN index pra performance no FTS
CREATE INDEX IF NOT EXISTS idx_chunk_fts
    ON documento_conhecimento_chunk USING GIN (fts);

-- 3. Função de busca híbrida com RRF
-- Retorna chunks ranqueados por fusão de cosine + FTS.
-- Args:
--   p_empresa_id: filtro tenant (obrigatório)
--   p_pasta_ids:  array de pasta_id (vazio = todas as pastas)
--   p_query:      texto cru pra FTS (websearch_to_tsquery)
--   p_query_vec:  embedding da query (vector)
--   p_k:          quantos retornar
DROP FUNCTION IF EXISTS kb_hybrid_search(BIGINT, BIGINT[], TEXT, vector, INT);
CREATE OR REPLACE FUNCTION kb_hybrid_search(
    p_empresa_id BIGINT,
    p_pasta_ids BIGINT[],
    p_query TEXT,
    p_query_vec vector,
    p_k INT DEFAULT 10
) RETURNS TABLE (
    documento_id BIGINT,
    chunk_id BIGINT,
    chunk_idx INT,
    conteudo TEXT,
    score_vector NUMERIC,
    score_text NUMERIC,
    rrf_score NUMERIC,
    rank_vector INT,
    rank_text INT
) AS $$
DECLARE
    rrf_k CONSTANT INT := 60;
    weight_vector CONSTANT NUMERIC := 1.0;
    weight_text CONSTANT NUMERIC := 1.5;
    fetch_n INT := GREATEST(p_k * 5, 20);
BEGIN
    RETURN QUERY
    WITH vec AS (
        SELECT
            c.id AS chunk_id,
            c.documento_id,
            c.chunk_idx,
            c.conteudo,
            (1 - (c.embedding <=> p_query_vec))::NUMERIC AS score,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> p_query_vec)::INT AS rnk
        FROM documento_conhecimento_chunk c
        JOIN documento_conhecimento d ON d.id = c.documento_id
        WHERE c.empresa_id = p_empresa_id
          AND d.ativo
          AND c.embedding IS NOT NULL
          AND (
              p_pasta_ids IS NULL
              OR cardinality(p_pasta_ids) = 0
              OR d.pasta_id = ANY(p_pasta_ids)
          )
        ORDER BY c.embedding <=> p_query_vec
        LIMIT fetch_n
    ),
    txt AS (
        SELECT
            c.id AS chunk_id,
            c.documento_id,
            c.chunk_idx,
            c.conteudo,
            ts_rank_cd(c.fts, websearch_to_tsquery('portuguese', p_query))::NUMERIC AS score,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(c.fts, websearch_to_tsquery('portuguese', p_query)) DESC
            )::INT AS rnk
        FROM documento_conhecimento_chunk c
        JOIN documento_conhecimento d ON d.id = c.documento_id
        WHERE c.empresa_id = p_empresa_id
          AND d.ativo
          AND c.fts @@ websearch_to_tsquery('portuguese', p_query)
          AND (
              p_pasta_ids IS NULL
              OR cardinality(p_pasta_ids) = 0
              OR d.pasta_id = ANY(p_pasta_ids)
          )
        ORDER BY ts_rank_cd(c.fts, websearch_to_tsquery('portuguese', p_query)) DESC
        LIMIT fetch_n
    ),
    fused AS (
        SELECT
            COALESCE(vec.chunk_id, txt.chunk_id) AS chunk_id,
            COALESCE(vec.documento_id, txt.documento_id) AS documento_id,
            COALESCE(vec.chunk_idx, txt.chunk_idx) AS chunk_idx,
            COALESCE(vec.conteudo, txt.conteudo) AS conteudo,
            COALESCE(vec.score, 0)::NUMERIC AS score_vector,
            COALESCE(txt.score, 0)::NUMERIC AS score_text,
            (
                COALESCE(weight_vector / (rrf_k + vec.rnk), 0)
                + COALESCE(weight_text / (rrf_k + txt.rnk), 0)
            )::NUMERIC AS rrf_score,
            vec.rnk AS rank_vector,
            txt.rnk AS rank_text
        FROM vec
        FULL OUTER JOIN txt ON txt.chunk_id = vec.chunk_id
    )
    SELECT
        f.documento_id,
        f.chunk_id,
        f.chunk_idx,
        f.conteudo,
        f.score_vector,
        f.score_text,
        f.rrf_score,
        f.rank_vector,
        f.rank_text
    FROM fused f
    ORDER BY f.rrf_score DESC
    LIMIT p_k;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION kb_hybrid_search IS
    'Busca híbrida vector+FTS com RRF (K=60, peso vector=1.0, text=1.5). Sprint N.1.';
