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
    // E1.8: registra a tentativa de login bloqueada antes de abortar.
    await recordLoginEvent({
      userId,
      eventType: "session_blocked_disabled",
      reason: "user account disabled",
    });
    throw new Error("Conta desativada. Contate o administrador.");
  }
}

/**
 * Insert em auth_login_event (E1.8). Best-effort: erros de DB não
 * propagam pra não quebrar o login fluxo principal.
 */
async function recordLoginEvent(params: {
  userId?: string | null;
  email?: string | null;
  eventType:
    | "login_success"
    | "login_failed"
    | "logout"
    | "password_reset_requested"
    | "password_changed"
    | "session_blocked_disabled";
  ipAddress?: string | null;
  userAgent?: string | null;
  reason?: string | null;
  metadata?: Record<string, unknown> | null;
}): Promise<void> {
  try {
    await authPool.query(
      `INSERT INTO auth_login_event
        (user_id, email, event_type, ip_address, user_agent, reason, metadata)
       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)`,
      [
        params.userId ?? null,
        params.email ?? null,
        params.eventType,
        params.ipAddress ?? null,
        params.userAgent ?? null,
        params.reason ?? null,
        params.metadata ? JSON.stringify(params.metadata) : null,
      ]
    );
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("[auth] recordLoginEvent failed", e);
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

  // Hook de sessão: bloqueia login de users com status=disabled (E1.7)
  // E registra eventos de login no auth_login_event (E1.8).
  databaseHooks: {
    session: {
      create: {
        before: async (session) => {
          await ensureUserActive(session.userId);
          return { data: session };
        },
        after: async (session) => {
          // Login bem sucedido — registra evento com IP/UA da session.
          await recordLoginEvent({
            userId: session.userId,
            eventType: "login_success",
            ipAddress: session.ipAddress ?? null,
            userAgent: session.userAgent ?? null,
          });
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
