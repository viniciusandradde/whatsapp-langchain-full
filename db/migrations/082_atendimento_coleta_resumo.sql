-- Mig 082 — Resumo final da coleta (visível no drawer pro atendente)
--
-- Quando wizard termina (cliente respondeu a última pergunta), o
-- conteúdo do `coleta_estado.respostas` é movido pra cá como snapshot
-- imutável. O drawer `/atendimento` lê esse JSONB e exibe como bloco
-- "Coleta prévia" no topo do histórico — visível pro atendente humano,
-- NÃO vai pro chat do cliente.
--
-- Schema sugerido: {item_id, item_label, respostas: {save_as: {label, valor}}, completed_at}

ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS coleta_resumo JSONB DEFAULT NULL;

COMMENT ON COLUMN atendimento.coleta_resumo IS
    'Snapshot imutável das respostas do wizard de coleta. NULL = sem '
    'coleta. Exibido no drawer /atendimento como bloco "Coleta prévia".';
