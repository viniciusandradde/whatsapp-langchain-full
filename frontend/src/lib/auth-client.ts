/**
 * Cliente de autenticação para componentes client-side.
 *
 * Exporta hooks e funções para login, logout e acesso à sessão.
 * O baseURL aponta para o próprio frontend (Next.js),
 * que repassa as chamadas ao Better Auth via /api/auth/[...all].
 */
import { createAuthClient } from "better-auth/react";

export const {
  changePassword,
  signIn,
  signOut,
  useSession,
} = createAuthClient();
