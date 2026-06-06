-- Config de integrações GLOBAIS da plataforma (sem empresa_id), editáveis pelo
-- superadmin via UI em vez de só env var. 1º uso: Asaas (billing da plataforma —
-- conta única que fatura as empresas-clientes; NÃO é per-empresa).
--
-- Credenciais cifradas (Fernet, integrations/crypto) em config_encrypted. SEM RLS
-- de propósito: é config global, não tem empresa_id — o acesso é protegido pelo
-- gate `is_superadmin` na rota. chat_nexus_app recebe CRUD automaticamente via
-- ALTER DEFAULT PRIVILEGES (mig 100), pois a tabela é criada pelo migrator.
--
-- Precedência: o billing lê esta tabela PRIMEIRO, env vars (ASAAS_*) como fallback.
CREATE TABLE IF NOT EXISTS platform_integration_config (
    slug             TEXT PRIMARY KEY,
    config_encrypted TEXT        NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by       TEXT
);

COMMENT ON TABLE platform_integration_config IS
    'Config de integrações GLOBAIS da plataforma (não per-empresa), cifradas '
    '(Fernet). Ex.: slug=asaas (billing). DB tem precedência sobre env vars.';
