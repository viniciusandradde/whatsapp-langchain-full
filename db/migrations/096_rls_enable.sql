-- Sprint A — Postgres RLS como fail-safe (2026-05-22)
--
-- HABILITA Row-Level Security em 10 tabelas críticas com PII / dados de
-- negócio multi-tenant. Política PERMISSIVA por compatibilidade:
--
--   - Se `app.empresa_id` NÃO setado (current_setting retorna ''): row passa.
--     Permite código legado continuar funcionando enquanto migramos call
--     sites para usar `with_empresa_context()`.
--   - Se `app.empresa_id` setado: row precisa ter `empresa_id` igual.
--   - Se `app.bypass_rls = 'true'`: row passa sempre (superadmin).
--
-- Quando 100% dos call sites em shared/*.py e routes/*.py usarem o helper
-- de context, mig futura (097_rls_strict.sql) muda a política pra
-- ESTRITA — sem fallback no NULL.
--
-- FORCE ROW LEVEL SECURITY ON: aplica policy inclusive ao owner.
--
-- CAVEAT CRÍTICO: roles SUPERUSER ou com BYPASSRLS=true IGNORAM RLS
-- mesmo com FORCE — é regra do Postgres, não tem como contornar.
-- A app conecta como `postgres` que é SUPERUSER, portanto RLS hoje fica
-- INERTE em runtime — helper e policies não tem efeito até criar role
-- não-superuser.
--
-- Por que enable mesmo assim?
--   1) Infra/schema preparado — quando criar role `chat_nexus_app`
--      (sprint futura A.2: NOSUPERUSER + GRANTs + DATABASE_URL update),
--      RLS começa a valer automaticamente sem nova migration.
--   2) Tests de isolamento documentam o comportamento esperado (xfail
--      hoje, pass quando role mudar).
--   3) Backups/superuser tools continuam funcionando (bypass automático).
--
-- Sprint A.2 (pendente — bloqueia hospital go-live multi-cliente):
--   CREATE ROLE chat_nexus_app LOGIN PASSWORD '<secret>' NOSUPERUSER;
--   GRANT CONNECT ON DATABASE whatsapp_langchain TO chat_nexus_app;
--   GRANT USAGE ON SCHEMA public TO chat_nexus_app;
--   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
--     TO chat_nexus_app;
--   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO chat_nexus_app;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT,
--     UPDATE, DELETE ON TABLES TO chat_nexus_app;
--   ALTER DATABASE whatsapp_langchain SET row_security = on;
--   -- Atualizar DATABASE_URL pra usar chat_nexus_app em vez de postgres.
--
-- Por que essas 10 tabelas? Cobrem 95% da superfície de PII / dados sensíveis:
--   cliente (CPF/RG/email/phone)
--   atendimento (conversation history)
--   conexao (credentials_encrypted)
--   agente_ia (prompts, modelo config)
--   agendamento (datas marcadas pra paciente)
--   hook (URLs externas / payload de webhook)
--   documento_conhecimento (KB content)
--   lgpd_event_log (audit sensível)
--   audit_log (audit geral)
--   message_queue (toda mensagem inbound/outbound)

-- 1) Habilita + FORCE RLS em todas as tabelas críticas (idempotente).
-- FORCE faz com que a policy seja aplicada inclusive ao role owner
-- (postgres no nosso caso) — sem isso, RLS é skipped pro owner e teria
-- valor zero. Operações que precisam ignorar (migrations, backups) usam
-- explicitamente `with_empresa_context(pool, None, bypass_rls=True)`.

ALTER TABLE cliente ENABLE ROW LEVEL SECURITY;
ALTER TABLE cliente FORCE ROW LEVEL SECURITY;

ALTER TABLE atendimento ENABLE ROW LEVEL SECURITY;
ALTER TABLE atendimento FORCE ROW LEVEL SECURITY;

ALTER TABLE conexao ENABLE ROW LEVEL SECURITY;
ALTER TABLE conexao FORCE ROW LEVEL SECURITY;

ALTER TABLE agente_ia ENABLE ROW LEVEL SECURITY;
ALTER TABLE agente_ia FORCE ROW LEVEL SECURITY;

ALTER TABLE agendamento ENABLE ROW LEVEL SECURITY;
ALTER TABLE agendamento FORCE ROW LEVEL SECURITY;

ALTER TABLE hook ENABLE ROW LEVEL SECURITY;
ALTER TABLE hook FORCE ROW LEVEL SECURITY;

ALTER TABLE documento_conhecimento ENABLE ROW LEVEL SECURITY;
ALTER TABLE documento_conhecimento FORCE ROW LEVEL SECURITY;

ALTER TABLE lgpd_event_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE lgpd_event_log FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

ALTER TABLE message_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_queue FORCE ROW LEVEL SECURITY;

-- 2) Helper function — encapsula a lógica de match comum.
-- Cria policy por tabela (DROP IF EXISTS pra idempotência).

CREATE OR REPLACE FUNCTION _rls_tenant_match(row_empresa_id BIGINT)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    ctx_empresa TEXT;
    ctx_bypass TEXT;
BEGIN
    -- bypass explícito (superadmin context)
    ctx_bypass := current_setting('app.bypass_rls', true);
    IF ctx_bypass = 'true' THEN
        RETURN TRUE;
    END IF;

    -- empresa não setada → permissive (compatibility com call sites legados)
    ctx_empresa := current_setting('app.empresa_id', true);
    IF ctx_empresa IS NULL OR ctx_empresa = '' THEN
        RETURN TRUE;
    END IF;

    -- empresa setada → row precisa bater
    RETURN row_empresa_id = ctx_empresa::BIGINT;
END;
$$;

COMMENT ON FUNCTION _rls_tenant_match(BIGINT) IS
    'Sprint A RLS helper. Retorna true se row pertence à empresa do '
    'context atual (`SET LOCAL app.empresa_id = X`) ou se bypass '
    'explícito (`SET LOCAL app.bypass_rls = true`) ou se nenhum '
    'context setado (modo permissive compat).';

-- 3) Policies — cobrem ALL operations (SELECT, INSERT, UPDATE, DELETE)
DROP POLICY IF EXISTS tenant_isolation ON cliente;
CREATE POLICY tenant_isolation ON cliente
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON atendimento;
CREATE POLICY tenant_isolation ON atendimento
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON conexao;
CREATE POLICY tenant_isolation ON conexao
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON agente_ia;
CREATE POLICY tenant_isolation ON agente_ia
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON agendamento;
CREATE POLICY tenant_isolation ON agendamento
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON hook;
CREATE POLICY tenant_isolation ON hook
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON documento_conhecimento;
CREATE POLICY tenant_isolation ON documento_conhecimento
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON lgpd_event_log;
CREATE POLICY tenant_isolation ON lgpd_event_log
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON audit_log;
CREATE POLICY tenant_isolation ON audit_log
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

DROP POLICY IF EXISTS tenant_isolation ON message_queue;
CREATE POLICY tenant_isolation ON message_queue
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

-- 4) Audit view — mostra status RLS por tabela
CREATE OR REPLACE VIEW rls_status AS
SELECT
    c.relname AS tabela,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS rls_force,
    (
        SELECT COUNT(*) FROM pg_policy p WHERE p.polrelid = c.oid
    ) AS policies_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND c.relrowsecurity = TRUE
ORDER BY c.relname;

COMMENT ON VIEW rls_status IS
    'Audit RLS: lista tabelas com row-level security ativada e contagem '
    'de policies. Esperado após Sprint A: 10 linhas. Próxima sprint '
    'expande pra 59 tabelas (todas com empresa_id).';
