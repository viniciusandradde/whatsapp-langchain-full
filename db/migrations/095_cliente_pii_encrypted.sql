-- Sprint D hardening (2026-05-22): PII em rest cifrada via Fernet, opt-in
-- por empresa.
--
-- Por que opt-in? Empresas sem LGPD-grade (ex: e-commerce básico) preferem
-- queries diretas em CPF (ex: dedup, busca). Hospital/saúde/financeiro
-- ativam o flag, paga overhead de decrypt em todas as leituras.
--
-- Estratégia:
--  - Adiciona colunas `cpf_encrypted`, `cnpj_encrypted`, `rg_encrypted`,
--    `data_nascimento_encrypted` (TEXT — Fernet ciphertext).
--  - Empresa ativa via `empresa.config->>'encrypt_pii' = 'true'`.
--  - shared/cliente.py lê: se flag on E encrypted col não nula → decrypt;
--    senão fallback no plain. Escrita: se flag on, cifra antes do INSERT
--    e zera plain col.
--  - Migração de dados retroativa fica como script ad-hoc por empresa
--    (não rola batch automático — pode quebrar queries existentes que
--    fazem dedupe em CPF plain).
--
-- Indexes: removidos sobre plain CPF (não existem hoje). Após opt-in,
-- buscas por CPF exato funcionam apenas via plain (encrypted é não-
-- determinístico).

ALTER TABLE cliente
    ADD COLUMN IF NOT EXISTS cpf_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS cnpj_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS rg_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS data_nascimento_encrypted TEXT;

COMMENT ON COLUMN cliente.cpf_encrypted IS
    'Fernet ciphertext (sprint D — opt-in via empresa.config.encrypt_pii).';
COMMENT ON COLUMN cliente.cnpj_encrypted IS
    'Fernet ciphertext (opt-in via empresa.config.encrypt_pii).';
COMMENT ON COLUMN cliente.rg_encrypted IS
    'Fernet ciphertext (opt-in via empresa.config.encrypt_pii).';
COMMENT ON COLUMN cliente.data_nascimento_encrypted IS
    'Fernet ciphertext da data ISO (opt-in via empresa.config.encrypt_pii).';

-- Helper view pra audit: mostra quantos clientes têm PII cifrado por empresa
CREATE OR REPLACE VIEW cliente_pii_audit AS
SELECT
    e.id AS empresa_id,
    e.nome AS empresa_nome,
    COALESCE((e.config->>'encrypt_pii')::boolean, false) AS encrypt_pii_enabled,
    COUNT(c.id) AS total_clientes,
    COUNT(c.cpf) FILTER (WHERE c.cpf IS NOT NULL) AS cpf_plain,
    COUNT(c.cpf_encrypted) FILTER (WHERE c.cpf_encrypted IS NOT NULL) AS cpf_encrypted,
    COUNT(c.rg) FILTER (WHERE c.rg IS NOT NULL) AS rg_plain,
    COUNT(c.rg_encrypted) FILTER (WHERE c.rg_encrypted IS NOT NULL) AS rg_encrypted
FROM empresa e
LEFT JOIN cliente c ON c.empresa_id = e.id
GROUP BY e.id, e.nome, e.config;

COMMENT ON VIEW cliente_pii_audit IS
    'Audit: PII em plain vs encrypted por empresa. Esperado: se '
    'encrypt_pii_enabled=true, plain → 0 após migração de dados.';
