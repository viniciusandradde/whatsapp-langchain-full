-- 201: classificação do lead no cadastro do cliente (funil + temperatura)
--
-- Decisão do dono (24/09/2026): funil de marketing + temperatura + pontuação,
-- com a IA sugerindo e o operador confirmando.
--
-- `lifecycle_stage` e `score` existem desde a mig 038, com o funil em inglês
-- (lead/qualified/opportunity/customer/evangelist/churned) e sem uso: 0 de
-- 2.020 clientes em produção tinham valor em 24/09. O CHECK passa para o funil
-- usado no painel: lead → mql → sql → oportunidade → cliente | perdido. O
-- UPDATE abaixo converte qualquer valor antigo antes de trocar o CHECK.
--
-- `classificacao_origem`: 'ia' quando a tool `classificar_lead` do agente
-- gravou, 'manual' quando o operador salvou ou confirmou. A IA nunca
-- sobrescreve uma classificação manual.

SELECT set_config('app.bypass_rls', 'true', true);

ALTER TABLE cliente DROP CONSTRAINT IF EXISTS cliente_lifecycle_stage_check;

UPDATE cliente SET lifecycle_stage = CASE lifecycle_stage
        WHEN 'qualified' THEN 'mql'
        WHEN 'opportunity' THEN 'oportunidade'
        WHEN 'customer' THEN 'cliente'
        WHEN 'evangelist' THEN 'cliente'
        WHEN 'churned' THEN 'perdido'
        ELSE lifecycle_stage
    END
 WHERE lifecycle_stage IN ('qualified', 'opportunity', 'customer', 'evangelist', 'churned');

ALTER TABLE cliente
    ADD CONSTRAINT cliente_lifecycle_stage_check
    CHECK (lifecycle_stage IS NULL OR lifecycle_stage IN
           ('lead', 'mql', 'sql', 'oportunidade', 'cliente', 'perdido'));

ALTER TABLE cliente
    ADD COLUMN IF NOT EXISTS temperatura TEXT,
    ADD COLUMN IF NOT EXISTS classificacao_origem TEXT,
    ADD COLUMN IF NOT EXISTS classificacao_motivo TEXT,
    ADD COLUMN IF NOT EXISTS classificado_em TIMESTAMPTZ;

ALTER TABLE cliente DROP CONSTRAINT IF EXISTS cliente_temperatura_check;
ALTER TABLE cliente
    ADD CONSTRAINT cliente_temperatura_check
    CHECK (temperatura IS NULL OR temperatura IN ('frio', 'morno', 'quente'));

ALTER TABLE cliente DROP CONSTRAINT IF EXISTS cliente_classificacao_origem_check;
ALTER TABLE cliente
    ADD CONSTRAINT cliente_classificacao_origem_check
    CHECK (classificacao_origem IS NULL OR classificacao_origem IN ('manual', 'ia'));

CREATE INDEX IF NOT EXISTS idx_cliente_funil
    ON cliente (empresa_id, lifecycle_stage, temperatura);

COMMENT ON COLUMN cliente.lifecycle_stage IS 'Estágio do funil: lead, mql, sql, oportunidade, cliente, perdido (mig 201).';
COMMENT ON COLUMN cliente.temperatura IS 'Temperatura do lead: frio, morno, quente (mig 201).';
COMMENT ON COLUMN cliente.classificacao_origem IS 'Quem classificou por último: ia (sugestão do agente) ou manual (operador salvou/confirmou). A IA nunca sobrescreve manual.';
COMMENT ON COLUMN cliente.classificacao_motivo IS 'Frase curta da IA justificando a sugestão.';
