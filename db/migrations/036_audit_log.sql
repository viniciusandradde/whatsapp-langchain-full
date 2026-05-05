-- Fase 0.1: Audit log centralizado.
--
-- Registra todas as mutations sensíveis (e reads sensíveis tipo export
-- LGPD) com payload diff completo. Substitui o padrão pontual usado em
-- auth_login_event (mig 026) — esse continua existindo pra audit
-- específico de login, mas mutations gerais vão pra cá.
--
-- Convenção `action`: `<entity>.<verbo>` em snake_case.
--   ex: cliente.create, cliente.update, cliente.delete,
--       perfil.assign, atendimento.transfer, lgpd.export, lgpd.forget
--
-- payload_diff:
--   - create: { "after": {...} }
--   - update: { "before": {...}, "after": {...} }
--   - delete: { "before": {...} }
--   - read sensível: { "filters": {...}, "rows_returned": N }
--
-- Imutável: sem updated_at; rows nunca são alteradas. Cleanup via
-- retention policy (Fase 6).

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    user_id TEXT,                         -- auth.user.id; NULL pra ações de sistema
    action TEXT NOT NULL,                 -- 'cliente.update', 'lgpd.forget', etc
    entity_type TEXT NOT NULL,            -- 'cliente', 'atendimento', 'campanha'
    entity_id TEXT,                       -- ID do recurso afetado (string pra suportar UUIDs/composite)
    payload_diff JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip TEXT,                              -- request_id origem (capturado por middleware)
    user_agent TEXT,
    request_id TEXT,                      -- correlation X-Request-Id
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookups típicos: filtrar por empresa+entity+action no painel admin
CREATE INDEX IF NOT EXISTS idx_audit_empresa_entity
    ON audit_log (empresa_id, entity_type, at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_empresa_user
    ON audit_log (empresa_id, user_id, at DESC) WHERE user_id IS NOT NULL;

-- Search por entity específico (audit trail de "tudo que aconteceu com cliente 123")
CREATE INDEX IF NOT EXISTS idx_audit_entity_lookup
    ON audit_log (entity_type, entity_id, at DESC);
