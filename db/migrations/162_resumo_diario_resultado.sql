-- Resumo diário: o resultado da tentativa passa a ficar registrado.
--
-- Até aqui, a única prova de que o envio aconteceu (ou falhou) era uma linha
-- de log do worker — que morre a cada deploy, junto com o container. Em
-- 2026-08-03 isso deixou um diagnóstico sem resposta possível: a empresa
-- estava marcada como "enviada hoje" e não havia como saber se a mensagem
-- chegou ao WhatsApp, falhou, ou nem foi tentada.
--
-- Com o resultado no banco, a própria tela de configuração responde.
--
-- `tentativas` + `tentativas_dia` sustentam a retentativa: uma falha devolve
-- o dia (o agendamento tenta de novo no tick seguinte, 60s), até o teto. Sem
-- o teto, uma falha permanente — telefone inválido, instância desconectada —
-- viraria uma chamada por minuto contra o provedor até a virada do dia.
-- `tentativas_dia` guarda a data LOCAL a que o contador se refere, então ele
-- se reinicia sozinho na virada sem precisar de job de limpeza.
--
-- Sem bloco de RLS: `empresa` já tem ENABLE + FORCE + isolamento por tenant
-- desde a Sprint A.2, e ALTER TABLE não movimenta linha.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS resumo_diario_last_status TEXT,
    ADD COLUMN IF NOT EXISTS resumo_diario_last_error TEXT,
    ADD COLUMN IF NOT EXISTS resumo_diario_last_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resumo_diario_tentativas INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS resumo_diario_tentativas_dia DATE;

COMMENT ON COLUMN empresa.resumo_diario_last_status IS
    'Resultado da última tentativa de envio do resumo diário: ok ou erro. '
    'NULL = nunca tentado. Inclui o envio manual pelo botão de teste.';

COMMENT ON COLUMN empresa.resumo_diario_last_error IS
    'Mensagem do erro da última tentativa, exibida na tela de configuração. '
    'NULL quando a última tentativa deu certo.';

COMMENT ON COLUMN empresa.resumo_diario_tentativas IS
    'Tentativas falhas do agendamento no dia local de resumo_diario_tentativas_dia. '
    'Ao bater o teto, o dia é consumido e a retentativa para até amanhã.';
