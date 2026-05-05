-- E2.B: Departamentos hierárquicos + scope de atendimento por departamento.
--
-- Adições:
-- 1. `departamento.parent_id` self-FK pra hierarquia (tree). NULL = root.
--    Cascade SET NULL pra não derrubar subárvore quando pai sai.
-- 2. `usuario_departamento` (M:N user × departamento, escopo empresa).
--    Sem `assigned_by` por simplicidade; quem precisar audit usa
--    rbac/login_history. Constraint composta empresa_id pra isolar.
--
-- Como a permissão se conecta:
-- - Quando user tem `atendimento.scope.departamento` (do catálogo
--   permissoes), o backend filtra `list_atendimentos` pra só atendimentos
--   cujo `departamento_id` IN (departamentos do user + descendants
--   transitivos via recursive CTE).
-- - Quando user NÃO tem scope.departamento, vê todos da empresa que tiver
--   `atendimento.read` (compat com comportamento atual).

ALTER TABLE departamento
    ADD COLUMN IF NOT EXISTS parent_id BIGINT
        REFERENCES departamento(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_departamento_parent
    ON departamento (parent_id) WHERE parent_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS usuario_departamento (
    user_id TEXT NOT NULL,                     -- auth.user.id
    departamento_id BIGINT NOT NULL REFERENCES departamento(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, departamento_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_departamento_user_empresa
    ON usuario_departamento (user_id, empresa_id);
CREATE INDEX IF NOT EXISTS idx_usuario_departamento_dep
    ON usuario_departamento (departamento_id);
