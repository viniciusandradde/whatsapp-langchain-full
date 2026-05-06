-- Sprint 7 — Paridade ZigChat (IA Budget — governança custo mensal).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Cliente define limite mensal por empresa. Sistema verifica antes de cada
-- chamada LLM. Quando atinge alerta_pct (default 80%), notifica admin via
-- aviso. Quando estoura limite, executa acao_estouro:
--   - alertar: só registra, continua respondendo
--   - bloquear: corta IA, atendente humano assume
--   - redirecionar_menu: volta cliente pro menu de fallback (acao_limite_menu_id
--     no agente_ia define qual menu)

CREATE TABLE IF NOT EXISTS ia_budget (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Formato "YYYY-MM" pra busca rápida e índice unique
    ano_mes CHAR(7) NOT NULL,
    limite_usd NUMERIC(10,2) NOT NULL,
    consumo_usd NUMERIC(10,2) NOT NULL DEFAULT 0,
    -- O que fazer quando consumo >= limite_usd
    acao_estouro TEXT NOT NULL DEFAULT 'alertar'
        CHECK (acao_estouro IN ('alertar', 'bloquear', 'redirecionar_menu')),
    -- Percentual quando dispara alerta proativo (ex: 80 = avisa em 80%)
    alerta_pct INT NOT NULL DEFAULT 80
        CHECK (alerta_pct BETWEEN 1 AND 100),
    estourado_em TIMESTAMPTZ,
    alertado_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, ano_mes)
);

CREATE INDEX IF NOT EXISTS idx_ia_budget_empresa
    ON ia_budget (empresa_id, ano_mes DESC);
