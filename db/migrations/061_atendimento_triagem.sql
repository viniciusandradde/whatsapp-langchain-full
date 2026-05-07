-- 061_atendimento_triagem.sql
-- Triagem omnichannel: agente IA classifica atendimento e gera resumo
-- antes de transferir pro atendente humano.
--
-- Colunas em `atendimento`:
--   - classificacao: categoria livre (ex: "suporte_login", "venda_consulta")
--   - prioridade: baixa|media|alta|urgente (CHECK)
--   - sentimento: positivo|neutro|negativo|frustrado (CHECK)
--   - resumo_ia: bullets curtos gerados pelo agente ao chamar transfer_to_human
--   - triagem_completa: flag de transferência concluída
--   - triagem_at: timestamp da última atualização de classificação
--
-- Coluna em `agente_ia`:
--   - departamento_default_id: depto destino fixo quando o agente chamar
--     transfer_to_human. Determinístico — IA NÃO escolhe departamento.

ALTER TABLE atendimento
    ADD COLUMN classificacao TEXT,
    ADD COLUMN prioridade TEXT
        CHECK (prioridade IS NULL OR prioridade IN ('baixa','media','alta','urgente')),
    ADD COLUMN sentimento TEXT
        CHECK (sentimento IS NULL OR sentimento IN ('positivo','neutro','negativo','frustrado')),
    ADD COLUMN resumo_ia TEXT,
    ADD COLUMN triagem_completa BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN triagem_at TIMESTAMPTZ;

CREATE INDEX idx_atendimento_prioridade
    ON atendimento (empresa_id, prioridade)
    WHERE prioridade IS NOT NULL;

CREATE INDEX idx_atendimento_triagem_completa
    ON atendimento (empresa_id, triagem_completa)
    WHERE triagem_completa = TRUE;

ALTER TABLE agente_ia
    ADD COLUMN departamento_default_id BIGINT
        REFERENCES departamento(id) ON DELETE SET NULL;

CREATE INDEX idx_agente_ia_dep_default
    ON agente_ia (departamento_default_id)
    WHERE departamento_default_id IS NOT NULL;
