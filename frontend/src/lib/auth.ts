/**
 * Configuração server-side do Better Auth.
 *
 * Usa o mesmo PostgreSQL do projeto com schema lógico separado ("auth")
 * para manter as tabelas de autenticação isoladas das tabelas da aplicação.
 *
 * Este arquivo só roda no servidor — nunca no browser.
 */
import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { Pool } from "pg";

export const authPool = new Pool({
  connectionString: process.env.DATABASE_URL,
  options: "-c search_path=auth,public",
});

// Origens confiáveis adicionais (CSRF). BETTER_AUTH_URL é sempre confiável;
// BETTER_AUTH_TRUSTED_ORIGINS aceita CSV pra cenários multi-host (LAN, tunnel, etc).
const trustedOrigins = (process.env.BETTER_AUTH_TRUSTED_ORIGINS ?? "")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

/**
 * Hook that blocks session creation when the user is `disabled` (E1.7).
 * Better Auth chama este callback antes de criar a row em auth.session;
 * lançar um Error aborta o sign-in flow com 401.
 */
async function ensureUserActive(userId: string): Promise<void> {
  const result = await authPool.query<{ status: string }>(
    `SELECT status FROM auth."user" WHERE id = $1`,
    [userId]
  );
  const status = result.rows[0]?.status;
  if (status === "disabled") {
    throw new Error("Conta desativada. Contate o administrador.");
  }
}

export const auth = betterAuth({
  // Conecta ao mesmo PostgreSQL, mas usa o schema "auth" para separação lógica.
  // O search_path garante que as tabelas do Better Auth (user, session, account, etc.)
  // ficam em auth.user, auth.session — sem conflito com as tabelas da aplicação.
  database: authPool,

  trustedOrigins,

  emailAndPassword: {
    enabled: true,
    disableSignUp: true,

    // Reset de senha sem SMTP (E1.7 finalizar):
    // O Better Auth chama este callback ao invés de mandar email; aqui
    // persistimos o link em auth.password_reset_pending pro admin
    // ler via /api/admin/users/{id}/reset-link (server action) e
    // compartilhar com o user pelo canal que preferir.
    //
    // O link persiste até o user usar OU expirar (1h padrão).
    sendResetPassword: async ({ user, url, token }) => {
      const expiresAt = new Date(Date.now() + 60 * 60 * 1000); // 1h
      await authPool.query(
        `INSERT INTO auth.password_reset_pending
            (user_id, token, url, expires_at, created_at)
         VALUES ($1, $2, $3, $4, NOW())
         ON CONFLICT (user_id) DO UPDATE
            SET token = EXCLUDED.token,
                url = EXCLUDED.url,
                expires_at = EXCLUDED.expires_at,
                created_at = NOW()`,
        [user.id, token, url, expiresAt]
      );
    },
  },

  // Hook de sessão: bloqueia login de users com status=disabled.
  // Quando admin desativa, set_user_status() já remove sessões existentes
  // (auth.session DELETE cascata); este hook fecha o caminho de re-login.
  databaseHooks: {
    session: {
      create: {
        before: async (session) => {
          await ensureUserActive(session.userId);
          return { data: session };
        },
      },
    },
  },

  // Rate limit nativo do Better Auth pra mitigar brute-force no /sign-in.
  // Padrão é por IP; configuração custom em /sign-in/email é mais agressiva
  // (5 tentativas / 15 min) que o default global (10 / minuto).
  rateLimit: {
    enabled: true,
    window: 60, // 60s window default
    max: 30,    // 30 req/min por IP em qualquer rota auth
    customRules: {
      "/sign-in/email": { window: 900, max: 5 },         // 5 tentativas / 15 min
      "/sign-up/email": { window: 900, max: 3 },         // 3 / 15 min (mesmo com disableSignUp)
      "/forget-password": { window: 3600, max: 3 },      // 3 / hora
      "/reset-password": { window: 3600, max: 5 },       // 5 / hora
    },
  },

  // nextCookies permite que Server Actions e Route Handlers
  // gerenciem cookies de sessão automaticamente
  plugins: [nextCookies()],
});
