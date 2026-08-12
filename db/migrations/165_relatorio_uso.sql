-- Relatório mensal de uso: o que a plataforma processou para cada cliente.
--
-- Volume de mensagens, arquivos lidos, tempo de resposta e disponibilidade —
-- um documento que o cliente recebe pelo WhatsApp e arquiva. Nasceu de um
-- relatório montado à mão para a empresa 1018, que valeu a pena o suficiente
-- para virar módulo.
--
-- O agendamento espelha o resumo diário (migs 135 + 162), com uma diferença
-- que muda o significado da coluna de claim: `relatorio_uso_last_sent` guarda
-- o PRIMEIRO DIA DA COMPETÊNCIA já enviada ('2026-07-01'), não a data do
-- envio. É isso que torna o claim idempotente por mês — reenviar julho depois
-- de agosto exige limpar a coluna, e não é acidente.
--
-- `relatorio_uso_dia` é o dia do mês em que o envio dispara; o padrão 1 manda
-- no primeiro dia, com o mês anterior fechado.
--
-- Sem bloco de RLS: `empresa` já tem ENABLE + FORCE + isolamento por tenant
-- desde a Sprint A.2, e ALTER TABLE não movimenta linha.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS relatorio_uso_ativo BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS relatorio_uso_telefone TEXT,
    ADD COLUMN IF NOT EXISTS relatorio_uso_dia INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS relatorio_uso_horario TIME NOT NULL DEFAULT '09:00',
    ADD COLUMN IF NOT EXISTS relatorio_uso_tz TEXT NOT NULL DEFAULT 'America/Campo_Grande',
    ADD COLUMN IF NOT EXISTS relatorio_uso_last_sent DATE,
    ADD COLUMN IF NOT EXISTS relatorio_uso_last_status TEXT,
    ADD COLUMN IF NOT EXISTS relatorio_uso_last_error TEXT,
    ADD COLUMN IF NOT EXISTS relatorio_uso_last_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS relatorio_uso_tentativas INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS relatorio_uso_tentativas_mes DATE;

COMMENT ON COLUMN empresa.relatorio_uso_last_sent IS
    'Primeiro dia da competência já enviada (2026-07-01 = julho enviado). '
    'NÃO é a data do envio: é o que torna o claim mensal idempotente.';

COMMENT ON COLUMN empresa.relatorio_uso_dia IS
    'Dia do mês em que o envio automático dispara. 1 = primeiro dia, com o '
    'mês anterior já fechado.';

COMMENT ON COLUMN empresa.relatorio_uso_tentativas IS
    'Tentativas falhas do agendamento na competência de relatorio_uso_tentativas_mes. '
    'Ao bater o teto, a competência é consumida e a retentativa para até o mês seguinte.';
