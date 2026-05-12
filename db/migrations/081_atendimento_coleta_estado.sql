-- Mig 081 — Estado runtime do wizard de coleta
--
-- Quando cliente escolhe item com `coleta_perguntas`, o worker grava aqui
-- o snapshot do estado: qual item, qual pergunta atual, respostas já dadas.
-- Inclui um snapshot `perguntas` do array original do item naquele
-- momento — assim se admin editar/deletar perguntas durante o atendimento,
-- o wizard em andamento continua válido sem quebrar.
--
-- NULL = sem wizard em andamento (estado normal).

ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS coleta_estado JSONB DEFAULT NULL;

COMMENT ON COLUMN atendimento.coleta_estado IS
    'Estado runtime do wizard de coleta. NULL = sem wizard. '
    'Schema: {item_id, idx, respostas, perguntas, started_at}';
