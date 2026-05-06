-- Sprint 7 — Paridade ZigChat (Telemetria LLM por execução).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Captura por chamada LLM:
--   - tokens_input + tokens_output + tokens_cached (prompt cache OpenAI/Anthropic)
--   - custo_total em USD (calculado client-side baseado em modelo_llm)
--   - duracao_ms latência
--   - tools_chamadas (lista nomes das tools executadas)
--   - status (success/error/timeout/rate_limit)
--
-- Diferente de audit_log (eventos genéricos): aqui é especifico LLM,
-- agregação fácil pra dashboards de custo/uso.

CREATE TABLE IF NOT EXISTS ia_execucao (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
    agente_ia_id BIGINT REFERENCES agente_ia(id) ON DELETE SET NULL,
    -- Modelo usado nessa execução (snapshot — mudanças no agente_ia depois
    -- não afetam telemetria histórica)
    modelo_provedor TEXT NOT NULL,
    modelo_nome TEXT NOT NULL,
    -- Tokens
    tokens_input INT NOT NULL DEFAULT 0,
    tokens_output INT NOT NULL DEFAULT 0,
    tokens_cached INT NOT NULL DEFAULT 0,
    -- Custo USD (8 casas decimais pra suportar modelos baratos como embeddings)
    custo_total NUMERIC(12,8),
    -- Latência
    duracao_ms INT,
    -- Tools chamadas nessa execução (snapshot)
    tools_chamadas TEXT[],
    -- Status final
    status TEXT NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'error', 'timeout', 'rate_limit', 'cancelled')),
    erro_msg TEXT,
    -- Metadata adicional (raw response, headers, etc)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ia_execucao_atendimento
    ON ia_execucao (atendimento_id, created_at DESC)
    WHERE atendimento_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ia_execucao_empresa_data
    ON ia_execucao (empresa_id, created_at DESC);

-- Index pra dashboards de custo (filtra por empresa+modelo, ordena por data)
CREATE INDEX IF NOT EXISTS idx_ia_execucao_modelo
    ON ia_execucao (empresa_id, modelo_provedor, created_at DESC);
