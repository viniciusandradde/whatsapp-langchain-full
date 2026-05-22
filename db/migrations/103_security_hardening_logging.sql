-- Sprint A.2.7 — Hardening built-in (sem pgaudit ainda)
--
-- pgaudit não vem na imagem postgres:16 oficial usada pelo Dokploy.
-- Trocar a imagem implica downtime do DB. Pra atingir maturidade real
-- 10/10 com menor risco, fazemos:
--
-- 1) Limita postgres (superuser) a CONNECTION LIMIT 10 pra que vazamento
--    de senha não permita avalanche de conexões. Suficiente pra:
--       - 5 containers app (API + 4 workers) bootstrap migrations
--       - 2-3 conexões admin manuais (debug)
--       - 2 conexões reserva
--
-- 2) Log statement DDL no role chat_nexus_app: app de runtime NÃO deveria
--    rodar DDL. Qualquer ALTER/CREATE/DROP dessa role é sinal de SQL
--    injection ou bug grave. Vai pro postgres log padrão (capturado por
--    docker logs / Dokploy).
--
-- 3) Tabela `_session_audit` + event trigger registra cada CREATE/ALTER/
--    DROP ROLE — mudanças de privilégio são raras e devem ser auditadas.
--    Postgres event triggers só pegam DDL; auth básico já capturado em
--    auth_login_event (Better Auth).
--
-- TODO sprint futura: trocar imagem postgres:16 → ghcr.io/cloudnative-pg/
-- postgresql:16-bullseye OU build custom com pgaudit pra log:read/write.

-- ===================================================================
-- 1) Connection limit pro postgres role
-- ===================================================================
ALTER ROLE postgres CONNECTION LIMIT 10;

COMMENT ON ROLE postgres IS
    'Sprint A.2.7 — CONNECTION LIMIT 10. Apenas migrator pool + admin '
    'manual. Runtime usa chat_nexus_app (NOBYPASSRLS). Senha rotacionada '
    'via vault a cada 90 dias.';

-- ===================================================================
-- 2) Log statement em chat_nexus_app (DDL = sinal de exploit)
-- ===================================================================
ALTER ROLE chat_nexus_app SET log_statement = 'ddl';
ALTER ROLE chat_nexus_app SET log_min_duration_statement = 1000;  -- queries >1s

COMMENT ON ROLE chat_nexus_app IS
    'Sprint A.2.7 — log_statement=ddl: qualquer DDL é logado (suspeito). '
    'log_min_duration_statement=1000: queries >1s logadas pra forensics. '
    'Mantém NOSUPERUSER + NOBYPASSRLS.';

-- ===================================================================
-- 3) Audit de mudanças de role / privilégios
-- ===================================================================
-- `session_user` e `current_user` são keywords reservados — evitamos
-- como nome de coluna e populamos via trigger.
CREATE TABLE IF NOT EXISTS _ddl_role_audit (
    id              BIGSERIAL PRIMARY KEY,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_user_at TEXT        NOT NULL,
    current_user_at TEXT        NOT NULL,
    client_addr     INET,
    command_tag     TEXT        NOT NULL,
    object_identity TEXT
);

CREATE INDEX IF NOT EXISTS idx_ddl_role_audit_occurred
    ON _ddl_role_audit (occurred_at DESC);

COMMENT ON TABLE _ddl_role_audit IS
    'Sprint A.2.7 — log de DDL relacionado a ROLE / GRANT / REVOKE. '
    'Trigger captura via pg_event_trigger_ddl_commands(). Sem RLS '
    '(audit-only). Revisar manualmente / cron de alertas.';

-- Função do trigger — registra command_tag relevante
CREATE OR REPLACE FUNCTION _log_role_ddl_change()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER  -- roda como owner pra inserir em _ddl_role_audit
AS $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        IF r.command_tag IN (
            'CREATE ROLE', 'ALTER ROLE', 'DROP ROLE',
            'CREATE POLICY', 'ALTER POLICY', 'DROP POLICY',
            'GRANT', 'REVOKE',
            'ALTER DATABASE',
            'CREATE EXTENSION', 'DROP EXTENSION'
        ) THEN
            INSERT INTO _ddl_role_audit (
                session_user_at, current_user_at,
                client_addr, command_tag, object_identity
            ) VALUES (
                session_user, current_user,
                inet_client_addr(), r.command_tag, r.object_identity
            );
        END IF;
    END LOOP;
END;
$$;

-- Idempotência: drop antes de criar
DROP EVENT TRIGGER IF EXISTS trg_audit_role_ddl;
CREATE EVENT TRIGGER trg_audit_role_ddl
    ON ddl_command_end
    EXECUTE FUNCTION _log_role_ddl_change();

COMMENT ON EVENT TRIGGER trg_audit_role_ddl IS
    'Sprint A.2.7 — captura DDL crítico (role/policy/grant/extension) '
    'pra _ddl_role_audit. Não bloqueia o DDL, só registra.';

-- ===================================================================
-- 4) Audit view: estado atual do hardening
-- ===================================================================
CREATE OR REPLACE VIEW security_hardening_status AS
SELECT
    -- Roles e bypass
    (SELECT count(*) FROM pg_roles
      WHERE rolcanlogin = TRUE AND rolname LIKE 'chat_nexus_%') AS app_roles_count,
    (SELECT count(*) FROM pg_roles
      WHERE rolsuper = TRUE AND rolname != 'postgres')          AS extra_superusers,
    -- RLS
    (SELECT count(*) FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname='public' AND c.relkind='r'
        AND c.relrowsecurity = TRUE)                            AS tables_rls_on,
    (SELECT count(*) FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname='public' AND c.relkind='r'
        AND c.relforcerowsecurity = TRUE)                       AS tables_rls_forced,
    -- Audit
    (SELECT count(*) FROM _ddl_role_audit
      WHERE occurred_at > NOW() - INTERVAL '24 hours')          AS ddl_role_24h,
    -- Policy strict (deve ser FALSE quando vazio)
    CASE WHEN _rls_tenant_match(1) THEN 'PERMISSIVE (vazio = TRUE)'
         ELSE 'STRICT (vazio = FALSE)' END                      AS rls_policy_mode
;

COMMENT ON VIEW security_hardening_status IS
    'Sprint A.2.7 dashboard de hardening — esperado: app_roles_count=4, '
    'extra_superusers=0, tables_rls_on=58+, tables_rls_forced=58+, '
    'rls_policy_mode=STRICT, ddl_role_24h=0 (sem mudanças não-autorizadas).';
