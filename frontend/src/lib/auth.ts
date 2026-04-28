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

export const auth = betterAuth({
  // Conecta ao mesmo PostgreSQL, mas usa o schema "auth" para separação lógica.
  // O search_path garante que as tabelas do Better Auth (user, session, account, etc.)
  // ficam em auth.user, auth.session — sem conflito com as tabelas da aplicação.
  database: authPool,

  emailAndPassword: {
    enabled: true,
    disableSignUp: true,
  },

  // nextCookies permite que Server Actions e Route Handlers
  // gerenciem cookies de sessão automaticamente
  plugins: [nextCookies()],
});
