-- 174 — fuso horário da empresa para as variáveis {{data.*}} do prompt
--
-- `build_render_context` montava `data.hoje`/`data.agora` em UTC. Um prompt que
-- pergunta "estamos dentro do horário de atendimento?" recebia 23h quando eram
-- 19h em Mato Grosso do Sul — e o agente respondia "fora do horário" no meio do
-- expediente.
--
-- O padrão de guardar o fuso por empresa já existe (`resumo_diario_tz` da mig
-- 135, `relatorio_uso_tz` da mig 165); esta coluna é o fuso GERAL da empresa,
-- usado por qualquer coisa que precise de hora local — hoje, as variáveis de
-- prompt. Default igual ao das outras duas para não mudar o comportamento de
-- quem já estava configurado.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'America/Campo_Grande';

-- Herda a escolha que o dono já fez no resumo diário: se ele configurou um fuso
-- ali, é o fuso da operação daquela empresa.
UPDATE empresa
   SET timezone = resumo_diario_tz
 WHERE resumo_diario_tz IS NOT NULL
   AND resumo_diario_tz <> ''
   AND timezone = 'America/Campo_Grande';

COMMENT ON COLUMN empresa.timezone IS
    'Fuso da operação (IANA). Usado nas variáveis {{data.*}} do prompt do agente.';
