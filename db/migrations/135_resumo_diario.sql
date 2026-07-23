-- Resumo diário por WhatsApp — config por empresa (feature pedida pelo
-- cliente Luis Fernando: receber às 22:30 um resumo dos atendimentos do dia
-- no número pessoal dele).
--
-- O job roda no worker (loop periódico, ver worker/main.py::_resumo_diario_loop):
-- no horário configurado (fuso da empresa, dias marcados), monta o resumo do
-- dia e envia PELA CONEXÃO PADRÃO da empresa pro telefone configurado.
-- `resumo_diario_last_sent` guarda a DATA LOCAL do último envio — é o guard
-- de idempotência (1 envio por dia, mesmo com múltiplos workers).

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS resumo_diario_ativo BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS resumo_diario_telefone TEXT,
    ADD COLUMN IF NOT EXISTS resumo_diario_horario TIME NOT NULL DEFAULT '22:30',
    -- Dias ISO (1=segunda ... 7=domingo); default seg-sex
    ADD COLUMN IF NOT EXISTS resumo_diario_dias INT[] NOT NULL DEFAULT '{1,2,3,4,5}',
    ADD COLUMN IF NOT EXISTS resumo_diario_tz TEXT NOT NULL DEFAULT 'America/Campo_Grande',
    ADD COLUMN IF NOT EXISTS resumo_diario_last_sent DATE;
