/**
 * Proxy de autenticação do painel administrativo (Next.js 16+).
 *
 * Verifica a existência do cookie de sessão do Better Auth.
 * Se ausente, redireciona para /login.
 *
 * Apenas checa o cookie (não faz chamada ao banco) para não
 * bloquear requests com latência de I/O. A validação completa
 * da sessão acontece nas pages/Server Components.
 */
import { NextRequest, NextResponse } from "next/server";
import { getSessionCookie } from "better-auth/cookies";

export function proxy(request: NextRequest) {
  const sessionCookie = getSessionCookie(request);

  if (!sessionCookie) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// Protege todas as rotas do painel exceto login, API e arquivos estáticos
export const config = {
  matcher: [
    "/((?!login|api|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|gif|webp|ico)$).*)",
  ],
};
