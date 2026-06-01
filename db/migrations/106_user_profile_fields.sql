-- Sprint U.1 — Campos perfil de usuário + tracking de login
--
-- ALTER auth."user" pra suportar UI completa de cadastro (paridade ZigChat):
-- - `telefone` (TEXT, opcional) — pra contato direto via WhatsApp
-- - `last_login_at` (TIMESTAMPTZ) — exibir "último acesso" na listagem
--
-- Better Auth não enxerga campos custom — acessamos via SQL direto.
-- Campos `name`, `email`, `image` continuam gerenciados pelo Better Auth.
--
-- Trigger: atualiza `last_login_at` quando uma nova session é criada.
-- Backup do hook em frontend/lib/auth.ts:databaseHooks.session.create —
-- garantia DB-level resiste a bypass da app, debug manual, etc.

ALTER TABLE auth."user"
    ADD COLUMN IF NOT EXISTS telefone TEXT,
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS avatar_path TEXT;

COMMENT ON COLUMN auth."user".telefone IS
    'Sprint U — telefone E.164 opcional (+5511999999999). Pra contato '
    'admin↔atendente via WhatsApp. Não enviado pra Better Auth.';
COMMENT ON COLUMN auth."user".last_login_at IS
    'Sprint U — timestamp da última session.created. Atualizado via trigger '
    '+ hook frontend (defesa em profundidade).';
COMMENT ON COLUMN auth."user".avatar_path IS
    'Sprint U — path local relativo a /uploads/avatars/{user_id}.png. '
    'Quando NULL, UI usa fallback com inicial do nome. Better Auth tem '
    'campo `image` (URL externa); usamos avatar_path pra upload local.';

-- Trigger: atualiza last_login_at em INSERT em auth.session
CREATE OR REPLACE FUNCTION auth._update_user_last_login()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE auth."user"
       SET last_login_at = NOW()
     WHERE id = NEW."userId";
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_session_update_last_login ON auth.session;
CREATE TRIGGER trg_session_update_last_login
    AFTER INSERT ON auth.session
    FOR EACH ROW
    EXECUTE FUNCTION auth._update_user_last_login();

COMMENT ON FUNCTION auth._update_user_last_login() IS
    'Sprint U — DB-level tracking de último login. Idempotente (sem '
    'race condition em sessions concorrentes — UPDATE simples).';

-- Backfill last_login_at com a session mais recente conhecida
UPDATE auth."user" u
   SET last_login_at = (
       SELECT MAX(s."createdAt") FROM auth.session s WHERE s."userId" = u.id
   )
 WHERE last_login_at IS NULL
   AND EXISTS (SELECT 1 FROM auth.session s WHERE s."userId" = u.id);

-- Index pra ordenação na listagem (recente primeiro)
CREATE INDEX IF NOT EXISTS idx_user_last_login_desc
    ON auth."user" (last_login_at DESC NULLS LAST);
