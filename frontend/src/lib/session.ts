/**
 * Validacao de sessao server-side.
 *
 * Centraliza a verificacao real da sessao do Better Auth para uso
 * em Server Components e Route Handlers. Diferente do proxy.ts
 * (que so checa o cookie), aqui fazemos a chamada ao banco para
 * confirmar que a sessao e valida.
 */
import "server-only";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

/**
 * Retorna a sessao validada ou redireciona para /login.
 *
 * Deve ser chamada no inicio de cada Server Component e Route Handler
 * que precisa de autenticacao. Faz a validacao completa (banco de dados),
 * nao apenas checagem de cookie.
 */
export async function requireSession() {
  ensureFrontendRuntimeConfig();

  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session) {
    redirect("/login");
  }

  return session;
}
