-- 193: ADR-005 leva E — vigência do plano e rebaixamento automático.
--
-- `empresa.plano_valido_ate` (DATE, "válido até o dia X inclusive"; NULL =
-- sem vencimento — é o estado de TODAS as empresas hoje, e nada muda para
-- elas até o superadmin registrar um pagamento na leva F ou fixar a data à
-- mão). O worker avisa em D-7, D-3 e D0 (WhatsApp do resumo diário +
-- banner no painel + aviso ao superadmin) e, 5 dias depois do vencimento
-- sem renovação, rebaixa para Free.
--
-- O claim dos avisos é por ETAPA e amarrado à data a que se refere
-- (`plano_aviso_vencimento_ref`): quando a data muda (renovação), a etapa
-- gravada deixa de valer sozinha — sem precisar lembrar de zerar.
--
-- `transacao` ganha o período coberto (a leva F grava ao registrar o
-- pagamento). As colunas de checkout/Pix da versão inicial da ADR NÃO
-- entram: com planos hospedados (D7) não há QR nem link por transação.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS plano_valido_ate DATE,
    ADD COLUMN IF NOT EXISTS plano_aviso_vencimento_etapa TEXT,
    ADD COLUMN IF NOT EXISTS plano_aviso_vencimento_ref DATE,
    ADD COLUMN IF NOT EXISTS plano_aviso_vencimento_em TIMESTAMPTZ;

COMMENT ON COLUMN empresa.plano_valido_ate IS
    'ADR-005 leva E: último dia (inclusive) em que o plano pago vale; NULL = sem vencimento (cortesia/legado)';
COMMENT ON COLUMN empresa.plano_aviso_vencimento_etapa IS
    'último aviso de vencimento enviado (d7 | d3 | d0 | rebaixado) para a data em plano_aviso_vencimento_ref';
COMMENT ON COLUMN empresa.plano_aviso_vencimento_ref IS
    'plano_valido_ate a que a etapa gravada se refere — data diferente = etapa não vale';

ALTER TABLE empresa
    DROP CONSTRAINT IF EXISTS empresa_plano_aviso_vencimento_etapa_check,
    ADD CONSTRAINT empresa_plano_aviso_vencimento_etapa_check
        CHECK (plano_aviso_vencimento_etapa IS NULL
               OR plano_aviso_vencimento_etapa IN ('d7', 'd3', 'd0', 'rebaixado'));

-- O job do worker varre só quem tem data: índice parcial mantém a leitura
-- barata mesmo com a tabela crescendo.
CREATE INDEX IF NOT EXISTS idx_empresa_plano_valido_ate
    ON empresa (plano_valido_ate)
    WHERE plano_valido_ate IS NOT NULL;

ALTER TABLE transacao
    ADD COLUMN IF NOT EXISTS periodo_inicio DATE,
    ADD COLUMN IF NOT EXISTS periodo_fim DATE;

COMMENT ON COLUMN transacao.periodo_inicio IS 'ADR-005 leva E/F: 1º dia coberto pelo pagamento';
COMMENT ON COLUMN transacao.periodo_fim IS 'ADR-005 leva E/F: último dia coberto (vira empresa.plano_valido_ate)';
