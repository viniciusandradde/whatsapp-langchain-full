-- 178 — Catálogo OpenRouter dentro do Nexus (módulo Saúde de IA, Fatia 1).
--
-- Hoje o catálogo de modelos é manual (`modelo_llm`, alimentado por migration)
-- e nenhum job consulta o OpenRouter: `CURATED_MODELS` e a tabela já
-- divergiram (grok/llama num, não no outro) e cada preço novo exige SQL à mão.
-- Estas tabelas trazem o catálogo COMPLETO (103 provedores, ~388 modelos, com
-- benchmarks Artificial Analysis embutidos) e a série temporal de saúde por
-- endpoint (uptime, latência p50..p99, throughput) — a base do dashboard,
-- da comparação por provedor e dos alertas de degradação (fatias 2-4).
--
-- **Escopo de plataforma, sem `empresa_id` e sem RLS** — mesmo desenho de
-- `relatorio_producao` (mig 173): não é dado de tenant, fala do ecossistema
-- de modelos inteiro. Gate `is_superadmin` nas rotas.
--
-- O catálogo completo é SÓ observabilidade (decisão do dono, 2026-08-25):
-- a seleção pelas empresas continua na lista curada (`modelo_llm`), com
-- promoção explícita de admin — nunca automática.

-- 1) Provedores (GET /api/v1/providers — oficial, sem chave).
CREATE TABLE IF NOT EXISTS openrouter_provedor (
    slug               TEXT PRIMARY KEY,
    nome               TEXT NOT NULL,
    privacy_policy_url TEXT,
    tos_url            TEXT,
    status_page_url    TEXT,
    hq                 TEXT,
    datacenters        JSONB NOT NULL DEFAULT '[]'::jsonb,
    atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2) Modelos (GET /api/v1/models — oficial). `pricing` e `benchmarks` ficam
--    como JSONB verbatim: o schema do OpenRouter cresce (image_output,
--    input_cache_write_1h…) e achatar em colunas viraria migration a cada
--    novidade. As colunas extraídas são as que o painel filtra/ordena.
CREATE TABLE IF NOT EXISTS openrouter_modelo (
    slug                 TEXT PRIMARY KEY,          -- ex.: google/gemini-3.1-flash-lite
    canonical_slug       TEXT,                      -- permaslug datado; NÃO usar o slug puro em stats
    nome                 TEXT NOT NULL,
    descricao            TEXT,
    context_length       INT,
    input_modalities     TEXT[] NOT NULL DEFAULT '{}',
    output_modalities    TEXT[] NOT NULL DEFAULT '{}',
    supported_parameters TEXT[] NOT NULL DEFAULT '{}',
    pricing              JSONB NOT NULL DEFAULT '{}'::jsonb,
    benchmarks           JSONB NOT NULL DEFAULT '{}'::jsonb,  -- artificial_analysis.{intelligence,coding,agentic}_index
    criado_no_or         TIMESTAMPTZ,               -- campo `created` da API
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_or_modelo_nome ON openrouter_modelo (nome);

-- 3) Série temporal de saúde por endpoint (GET /models/{slug}/endpoints COM
--    chave — latência/throughput só populam autenticado; provado 2026-08-25).
--    Uma linha por (modelo, endpoint, tick). Retenção 90d aplicada no sync
--    diário — sem cron novo, padrão do cleanup inline de shared/rate_limit.py.
CREATE TABLE IF NOT EXISTS openrouter_endpoint_metrica (
    id            BIGSERIAL PRIMARY KEY,
    modelo_slug   TEXT NOT NULL,
    provider_tag  TEXT NOT NULL,                    -- ex.: google-vertex/global
    provider_nome TEXT NOT NULL,
    quantization  TEXT,
    status        TEXT,
    uptime_5m     NUMERIC(6,3),
    uptime_30m    NUMERIC(6,3),
    uptime_1d     NUMERIC(6,3),
    latencia      JSONB,                            -- {p50,p75,p90,p99} em ms
    throughput    JSONB,                            -- {p50,p75,p90,p99} em tok/s
    pricing       JSONB,
    coletado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_or_metrica_modelo
    ON openrouter_endpoint_metrica (modelo_slug, coletado_em DESC);
CREATE INDEX IF NOT EXISTS idx_or_metrica_coletado
    ON openrouter_endpoint_metrica (coletado_em);   -- pro cleanup de retenção

-- 4) Estado do sync (1 linha) — claim atômico do catálogo diário (padrão
--    resumo_diario) + carimbo pro painel mostrar "última sincronização".
CREATE TABLE IF NOT EXISTS openrouter_sync_estado (
    id                     INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    catalogo_sync_date     DATE,                    -- claim: 1 sync completo/dia
    catalogo_sync_at       TIMESTAMPTZ,
    catalogo_total_modelos INT,
    catalogo_total_provs   INT,
    metricas_sync_at       TIMESTAMPTZ,
    erro                   TEXT
);
INSERT INTO openrouter_sync_estado (id) VALUES (1) ON CONFLICT DO NOTHING;
