-- Fase 1.A: Schema expansion — Cliente +~30 campos.
--
-- Antes: cliente tinha 11 colunas (id, empresa_id, telefone, nome, email,
--   doc, status, config, created_at, updated_at + tags via tabela).
-- Depois: ~40 colunas cobrindo PF/PJ, endereço completo, segmentação
--   comercial (lifecycle/score/source), social, contato secundário,
--   responsável, locale/timezone.
--
-- Não-quebra-cadeia:
--   - Todas as novas colunas são NULLABLE (sem default obrigatório que
--     mude semântica); writes existentes continuam funcionando.
--   - `doc` legacy é mantido (já em uso); novos `cpf`/`cnpj` são
--     campos separados (mais correto pra validação + busca).
--
-- Convenção:
--   - tipo_pessoa: 'PF' | 'PJ' | NULL (não decidido)
--   - cpf/cnpj: armazenados SEM formatação (só dígitos) — UI formata
--   - cep: SEM hífen (só dígitos)
--   - lifecycle_stage: lead | qualified | customer | churned (free-text
--     com check; admin pode customizar via JSONB futuro)
--   - score: 0-100 (intent/quality score atribuído pelo agente)

ALTER TABLE cliente
    -- Identificação PF/PJ
    ADD COLUMN IF NOT EXISTS tipo_pessoa TEXT
        CHECK (tipo_pessoa IS NULL OR tipo_pessoa IN ('PF', 'PJ')),
    ADD COLUMN IF NOT EXISTS cpf TEXT,
    ADD COLUMN IF NOT EXISTS cnpj TEXT,
    ADD COLUMN IF NOT EXISTS rg TEXT,
    ADD COLUMN IF NOT EXISTS razao_social TEXT,
    ADD COLUMN IF NOT EXISTS nome_fantasia TEXT,
    ADD COLUMN IF NOT EXISTS data_nascimento DATE,
    ADD COLUMN IF NOT EXISTS genero TEXT,

    -- Endereço estruturado
    ADD COLUMN IF NOT EXISTS cep TEXT,
    ADD COLUMN IF NOT EXISTS logradouro TEXT,
    ADD COLUMN IF NOT EXISTS numero TEXT,
    ADD COLUMN IF NOT EXISTS complemento TEXT,
    ADD COLUMN IF NOT EXISTS bairro TEXT,
    ADD COLUMN IF NOT EXISTS cidade TEXT,
    ADD COLUMN IF NOT EXISTS uf CHAR(2),
    ADD COLUMN IF NOT EXISTS pais TEXT DEFAULT 'BR',

    -- Comercial / lifecycle
    ADD COLUMN IF NOT EXISTS segmento TEXT,
    ADD COLUMN IF NOT EXISTS lifecycle_stage TEXT
        CHECK (lifecycle_stage IS NULL OR lifecycle_stage IN
               ('lead', 'qualified', 'opportunity', 'customer', 'evangelist', 'churned')),
    ADD COLUMN IF NOT EXISTS score SMALLINT
        CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS responsavel_user_id TEXT,
    ADD COLUMN IF NOT EXISTS valor_estimado_brl NUMERIC(12, 2),

    -- Social / canais alternativos
    ADD COLUMN IF NOT EXISTS instagram TEXT,
    ADD COLUMN IF NOT EXISTS linkedin TEXT,
    ADD COLUMN IF NOT EXISTS facebook TEXT,
    ADD COLUMN IF NOT EXISTS website TEXT,
    ADD COLUMN IF NOT EXISTS email_alternativo TEXT,
    ADD COLUMN IF NOT EXISTS telefone_alternativo TEXT,

    -- Localização / preferências
    ADD COLUMN IF NOT EXISTS locale TEXT DEFAULT 'pt-BR',
    ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/Sao_Paulo',
    ADD COLUMN IF NOT EXISTS avatar_url TEXT,

    -- Tracking
    ADD COLUMN IF NOT EXISTS last_interaction_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS notes TEXT;  -- texto livre adicional


-- Indexes pra buscas comuns
CREATE INDEX IF NOT EXISTS idx_cliente_cpf
    ON cliente (empresa_id, cpf) WHERE cpf IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cliente_cnpj
    ON cliente (empresa_id, cnpj) WHERE cnpj IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cliente_lifecycle
    ON cliente (empresa_id, lifecycle_stage)
    WHERE lifecycle_stage IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cliente_responsavel
    ON cliente (empresa_id, responsavel_user_id)
    WHERE responsavel_user_id IS NOT NULL;

-- UNIQUE constraints PARTIAL (só quando preenchido) — evita duplicação
-- de mesmo CPF/CNPJ na mesma empresa, sem bloquear NULLs.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cliente_empresa_cpf
    ON cliente (empresa_id, cpf) WHERE cpf IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cliente_empresa_cnpj
    ON cliente (empresa_id, cnpj) WHERE cnpj IS NOT NULL;
