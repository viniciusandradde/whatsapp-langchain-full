-- Mig 084 — Audit trail de governança (RBAC, members, departamentos)
--
-- Toda mudança crítica de governança (atribuição de perfil, mudança de
-- role legacy, ativação/desativação de membro, grant/revoke de
-- superadmin, vinculação a departamento) gera 1 row aqui.
--
-- LGPD/compliance: mantém trail de "quem mudou o que de quem". Diferente
-- da `audit_log` genérica (mig 026 login_event + audit_log) — esta é
-- exclusiva pra mudanças de permissões/escopo, mais rica em contexto.

CREATE TABLE IF NOT EXISTS audit_governanca (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    actor_user_id TEXT NOT NULL,            -- quem fez a mudança
    target_user_id TEXT,                    -- quem foi afetado (NULL pra ações company-wide)
    action TEXT NOT NULL,                   -- perfil.sync | depto.sync | role.change |
                                            -- superadmin.grant | superadmin.revoke |
                                            -- member.add | member.remove | member.disable |
                                            -- member.enable
    entity_type TEXT,                       -- 'usuario_perfil' | 'usuario_departamento' |
                                            -- 'empresa_membro' | 'auth.user'
    entity_id TEXT,                         -- ID do registro afetado (string pra suportar UUID)
    payload_before JSONB,                   -- snapshot antes (lista de perfis/deptos)
    payload_after JSONB,                    -- snapshot depois
    request_id TEXT,                        -- correlation com structlog (request_id middleware)
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE audit_governanca IS
    'Audit trail de mudanças de governança (RBAC, departamentos, members). '
    'Diferente da audit_log genérica — exclusiva pra rastreabilidade LGPD/compliance.';

-- Índices: lookups típicos do viewer
-- 1. "histórico do user X" (target)
CREATE INDEX IF NOT EXISTS idx_audit_gov_target_time
    ON audit_governanca (empresa_id, target_user_id, created_at DESC)
    WHERE target_user_id IS NOT NULL;

-- 2. "tudo que o admin Y fez" (actor)
CREATE INDEX IF NOT EXISTS idx_audit_gov_actor_time
    ON audit_governanca (actor_user_id, created_at DESC);

-- 3. "ações tipo superadmin.* na empresa" (filtro por action + período)
CREATE INDEX IF NOT EXISTS idx_audit_gov_empresa_action
    ON audit_governanca (empresa_id, action, created_at DESC);
