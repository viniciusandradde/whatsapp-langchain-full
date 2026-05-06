-- Sprint 8 — Paridade ZigChat (Empresa expand — fechamento do roadmap).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao empresa:
--   - menu_coleta_id: FK pra menu_chatbot — menu padrão de coleta inicial
--     da empresa (cliente novo cai aqui antes de chegar no agente)
--   - hook_id: FK pra hook — webhook genérico da empresa (ex: notificar
--     CRM externo de novos clientes)
--   - plano_id: FK pra plano (mig 059) — substitui empresa.plano TEXT
--     gradualmente
--   - razao_social, inscricao_estadual: dados fiscais
--   - endereco_fiscal_*: endereço fiscal completo (NF/billing)

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS menu_coleta_id BIGINT,
    ADD COLUMN IF NOT EXISTS hook_id BIGINT,
    ADD COLUMN IF NOT EXISTS plano_id BIGINT,
    -- Dados fiscais
    ADD COLUMN IF NOT EXISTS razao_social TEXT,
    ADD COLUMN IF NOT EXISTS inscricao_estadual TEXT,
    -- Endereço fiscal completo
    ADD COLUMN IF NOT EXISTS endereco_fiscal_cep TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_logradouro TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_numero TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_complemento TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_bairro TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_cidade TEXT,
    ADD COLUMN IF NOT EXISTS endereco_fiscal_uf CHAR(2);

-- FKs (definidas via DO pra ser idempotente)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_empresa_menu_coleta'
    ) THEN
        ALTER TABLE empresa
            ADD CONSTRAINT fk_empresa_menu_coleta
            FOREIGN KEY (menu_coleta_id)
            REFERENCES menu_chatbot(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_empresa_hook'
    ) THEN
        ALTER TABLE empresa
            ADD CONSTRAINT fk_empresa_hook
            FOREIGN KEY (hook_id)
            REFERENCES hook(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_empresa_plano'
    ) THEN
        ALTER TABLE empresa
            ADD CONSTRAINT fk_empresa_plano
            FOREIGN KEY (plano_id)
            REFERENCES plano(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Backfill: tenta vincular plano_id baseado no empresa.plano TEXT
UPDATE empresa e
   SET plano_id = p.id
  FROM plano p
 WHERE e.plano_id IS NULL
   AND LOWER(e.plano) = p.slug;
