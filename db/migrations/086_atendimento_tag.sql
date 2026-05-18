-- Sprint Atendimento UX (1.2) — Multi-tag por atendimento.
--
-- Reusa tabela `tag` existente (mig 052, hoje só usada via cliente_tag_v2).
-- Aplicação pode vir de: humano (atendente clica) ou IA (triagem classifica
-- e mapeia classificacao→tag por descricao). Coluna aplicado_por_ia
-- diferencia origens pra UI/audit.

CREATE TABLE IF NOT EXISTS atendimento_tag (
    atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    tag_id BIGINT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    aplicado_por_user_id TEXT,                     -- NULL se foi a IA
    aplicado_por_ia BOOLEAN NOT NULL DEFAULT FALSE,
    aplicado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (atendimento_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_atendimento_tag_tag
    ON atendimento_tag (tag_id, empresa_id);

CREATE INDEX IF NOT EXISTS idx_atendimento_tag_atendimento
    ON atendimento_tag (atendimento_id);
