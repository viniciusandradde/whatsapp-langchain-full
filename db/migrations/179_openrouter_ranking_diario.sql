-- 179 — Rankings diários do OpenRouter (módulo Saúde de IA, F3 parte 2).
--
-- Cache do dataset oficial `GET /api/v1/datasets/rankings-daily` (com chave):
-- tokens/dia dos ~51 modelos mais usados do OpenRouter, janela móvel de 30
-- dias. Guardar localmente compra duas coisas: (1) o dashboard não depende
-- da API a cada page-view; (2) a janela do OpenRouter é 30d, a nossa tabela
-- ACUMULA — com o tempo temos histórico que a API não devolve mais.
--
-- `model_permaslug` vem DATADO (ex.: deepseek/deepseek-v4-flash-20260731 —
-- versões do mesmo modelo trocam no meio da janela); `slug` é a base sem o
-- sufixo -YYYYMMDD, derivada no sync, pro join com `openrouter_modelo` e
-- com o curado. Agregações somam por slug.
--
-- Escopo de plataforma, sem empresa_id/RLS (padrão migs 173/178).

CREATE TABLE IF NOT EXISTS openrouter_ranking_diario (
    data            DATE NOT NULL,
    model_permaslug TEXT NOT NULL,
    slug            TEXT NOT NULL,
    total_tokens    BIGINT NOT NULL,
    coletado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (data, model_permaslug)
);
CREATE INDEX IF NOT EXISTS idx_or_ranking_slug
    ON openrouter_ranking_diario (slug, data DESC);

-- Claim do sync diário de rankings (mesmo padrão do catálogo na mig 178).
ALTER TABLE openrouter_sync_estado
    ADD COLUMN IF NOT EXISTS rankings_sync_date DATE,
    ADD COLUMN IF NOT EXISTS rankings_sync_at   TIMESTAMPTZ;
