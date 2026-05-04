-- E1.7: status do usuário (ativo/desativado).
--
-- Adiciona coluna `status` em auth.user. Default 'active' pra não
-- afetar usuários existentes. Bloqueio de login é feito no Better Auth
-- via callback `databaseHooks.user.create.after` ou via session check
-- (preferimos session check pra desbloquear automaticamente quando admin
-- reativa).
--
-- Status válidos:
-- - 'active'    → pode logar normalmente
-- - 'disabled'  → admin desativou (acesso bloqueado, sessões expiram)

ALTER TABLE auth."user"
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'disabled'));

CREATE INDEX IF NOT EXISTS idx_user_status
    ON auth."user" (status)
    WHERE status != 'active';
