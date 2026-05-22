-- Sprint A.2.1 — Cria 4 roles application (2026-05-22)
--
-- Hoje a aplicação conecta como `postgres` (SUPERUSER + BYPASSRLS).
-- Postgres ignora RLS pra esses roles independente de FORCE. Resultado:
-- mig 096 (RLS enabled) é inerte.
--
-- Esta mig prepara 4 roles least-privilege, criadas SEM senha (NOLOGIN).
-- Senhas são definidas via `scripts/setup_app_roles_passwords.py` lendo
-- env vars (CHAT_NEXUS_{APP,MIGRATOR,READONLY,AUDIT}_PASSWORD), que faz
-- `ALTER ROLE ... WITH LOGIN PASSWORD '<X>'` separadamente. Assim a
-- migration roda em qualquer ambiente sem expor secrets em SQL.
--
-- Roles:
--   chat_nexus_app       → API + Worker em runtime (CRUD, RLS-bound)
--   chat_nexus_migrator  → Aplicar migrations (DDL, RLS-bound)
--   chat_nexus_readonly  → BI / Grafana / dashboards (SELECT, RLS-bound)
--   chat_nexus_audit     → Compliance LGPD (cross-tenant SELECT, BYPASSRLS)
--
-- IDEMPOTENTE: pode rodar várias vezes; só cria role se não existe;
-- GRANTs são re-aplicados (sem efeito se já presentes).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chat_nexus_app') THEN
        CREATE ROLE chat_nexus_app NOLOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
            CONNECTION LIMIT 50;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chat_nexus_migrator') THEN
        CREATE ROLE chat_nexus_migrator NOLOGIN
            NOSUPERUSER CREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
            CONNECTION LIMIT 3;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chat_nexus_readonly') THEN
        CREATE ROLE chat_nexus_readonly NOLOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
            CONNECTION LIMIT 20;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chat_nexus_audit') THEN
        CREATE ROLE chat_nexus_audit NOLOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS NOREPLICATION
            CONNECTION LIMIT 5;
    END IF;
END $$;

COMMENT ON ROLE chat_nexus_app IS
    'Sprint A.2 — Runtime API + Worker. NOSUPERUSER + NOBYPASSRLS pra '
    'que RLS valha. Senha rotacionada via vault (anual mandatório). '
    'Setar via scripts/setup_app_roles_passwords.py.';
COMMENT ON ROLE chat_nexus_migrator IS
    'Sprint A.2 — Aplica migrations. NOBYPASSRLS — DDL e dados tenant-'
    'scoped precisam usar app.bypass_rls=true explicitamente quando '
    'necessário (rotina de backfill, etc).';
COMMENT ON ROLE chat_nexus_readonly IS
    'Sprint A.2 — Leitura BI/Grafana. NOBYPASSRLS — queries precisam '
    'setar app.empresa_id pra ver dados.';
COMMENT ON ROLE chat_nexus_audit IS
    'Sprint A.2 — Auditoria LGPD/compliance. BYPASSRLS pra ver '
    'cross-tenant. Acesso via VPN + 2FA recomendado em prod.';

-- ========== GRANTs ==========

GRANT CONNECT ON DATABASE whatsapp_langchain TO
    chat_nexus_app, chat_nexus_migrator, chat_nexus_readonly, chat_nexus_audit;

GRANT USAGE ON SCHEMA public TO
    chat_nexus_app, chat_nexus_migrator, chat_nexus_readonly, chat_nexus_audit;
GRANT USAGE ON SCHEMA auth TO
    chat_nexus_app, chat_nexus_migrator, chat_nexus_readonly, chat_nexus_audit;

-- app: CRUD em todas tabelas existentes
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO chat_nexus_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA auth TO chat_nexus_app;
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA public TO chat_nexus_app;
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA auth TO chat_nexus_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO chat_nexus_app;

-- migrator: tudo
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO chat_nexus_migrator;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA auth TO chat_nexus_migrator;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO chat_nexus_migrator;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA auth TO chat_nexus_migrator;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO chat_nexus_migrator;
GRANT CREATE ON SCHEMA public TO chat_nexus_migrator;
GRANT CREATE ON SCHEMA auth TO chat_nexus_migrator;

-- readonly: SELECT only
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chat_nexus_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA auth TO chat_nexus_readonly;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO chat_nexus_readonly;

-- audit: SELECT only + BYPASSRLS (já cobre cross-tenant)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chat_nexus_audit;
GRANT SELECT ON ALL TABLES IN SCHEMA auth TO chat_nexus_audit;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO chat_nexus_audit;

-- ========== Default privileges: tabelas FUTURAS herdam ==========
-- Aplicado pelo postgres (owner default das migs); quando migrator
-- virar dono, ALTER DEFAULT vai precisar ser repetido por ele.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO chat_nexus_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO chat_nexus_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO chat_nexus_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO chat_nexus_readonly, chat_nexus_audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO chat_nexus_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO chat_nexus_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON FUNCTIONS TO chat_nexus_migrator;

ALTER DEFAULT PRIVILEGES IN SCHEMA auth
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO chat_nexus_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth
    GRANT SELECT ON TABLES TO chat_nexus_readonly, chat_nexus_audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth
    GRANT ALL PRIVILEGES ON TABLES TO chat_nexus_migrator;

-- ========== row_security ON pra forçar avaliação ==========
ALTER ROLE chat_nexus_app SET row_security = on;
ALTER ROLE chat_nexus_readonly SET row_security = on;
ALTER ROLE chat_nexus_migrator SET row_security = on;

-- ========== Audit view ==========
CREATE OR REPLACE VIEW app_roles_status AS
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolbypassrls,
    rolconnlimit
FROM pg_roles
WHERE rolname LIKE 'chat_nexus_%'
ORDER BY rolname;

COMMENT ON VIEW app_roles_status IS
    'Sprint A.2 audit — esperado: 4 roles, sem rolsuper, sem rolbypassrls '
    '(exceto audit). rolcanlogin=false até script setar senhas.';
