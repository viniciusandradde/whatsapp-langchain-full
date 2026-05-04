-- E1.7 finalizar: cache de links de reset de senha pendentes.
--
-- Sem SMTP configurado (M9 convite por email cancelado), o admin precisa
-- de um caminho pra "esqueci a senha" do user. Solução: quando admin
-- clica "Gerar link de reset" em members-list, o frontend dispara
-- `auth.api.forgetPassword({email})` do Better Auth — o callback
-- `sendResetPassword` (em frontend/src/lib/auth.ts) NÃO envia email;
-- em vez disso PERSISTE o link aqui, e o action server retorna pro
-- admin copiar e enviar via WhatsApp/etc.
--
-- A tabela é um cache de 1 row por user (UPSERT) — só guarda o último
-- link pendente. Cleanup via cron ou query manual quando expires_at <
-- NOW().

CREATE TABLE IF NOT EXISTS auth.password_reset_pending (
    user_id TEXT PRIMARY KEY REFERENCES auth."user"(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    url TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_pending_expires
    ON auth.password_reset_pending (expires_at);
