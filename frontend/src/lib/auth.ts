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

export const auth = betterAuth({
  // Conecta ao mesmo PostgreSQL, mas usa o schema "auth" para separação lógica.
  // O search_path garante que as tabelas do Better Auth (user, session, account, etc.)
  // ficam em auth.user, auth.session — sem conflito com as tabelas da aplicação.
  database: authPool,

  trustedOrigins,

  emailAndPassword: {
    enabled: true,
    disableSignUp: true,
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
