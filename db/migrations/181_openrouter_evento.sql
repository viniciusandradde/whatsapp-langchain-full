-- 181 — Feed de novidades do ecossistema OpenRouter (hub Saúde de IA, F5).
--
-- O OpenRouter NÃO expõe notícias/anúncios por API oficial (provado
-- 2026-08-28: /announcements e /news são 404; só existem /providers,
-- /models, /models/{slug}/endpoints e /datasets/rankings-daily). O feed
-- daqui é gerado por DIFF entre syncs — determinístico e auditável:
--   modelo_novo / modelo_voltou / modelo_removido  (presença no catálogo)
--   preco_mudou / contexto_mudou                   (campos entre syncs)
--   entrou_top / saiu_top                          (top 20 dos rankings, por dia)
--
-- `openrouter_modelo.ativo` é o que torna "removido" um EVENTO e não um
-- alarme diário: ausente com ativo=TRUE gera o evento e desliga a flag;
-- no sync seguinte, ausente com ativo=FALSE é silêncio.
--
-- Escopo de plataforma, sem empresa_id/RLS (padrão migs 173/178-180).

CREATE TABLE IF NOT EXISTS openrouter_evento (
    id          BIGSERIAL PRIMARY KEY,
    tipo        TEXT NOT NULL,
    modelo_slug TEXT NOT NULL,
    detalhe     JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_or_evento_recentes
    ON openrouter_evento (criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_or_evento_modelo
    ON openrouter_evento (modelo_slug, criado_em DESC);

ALTER TABLE openrouter_modelo
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;
