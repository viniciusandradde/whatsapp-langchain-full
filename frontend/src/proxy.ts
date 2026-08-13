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

// Protege todas as rotas do painel exceto login, reset-password, API,
// assets estáticos e arquivos especiais do PWA.
//
// `reset-password` é público POR DESENHO: é onde a pessoa chega pelo link
// do convite de acesso (WhatsApp) ANTES de ter qualquer sessão. O que
// protege a página é o token de uso único do Better Auth, não o cookie.
//
// Cuidado: SW (`/sw.js`) e Manifest (`/manifest.webmanifest`) PRECISAM
// ser servidos com Content-Type correto sem redirect. Se caírem no
// middleware sem auth → redirect 307 pra /login → SW nunca registra,
// PWA NÃO fica installable. Esses paths são excluídos por nome.
export const config = {
  matcher: [
    "/((?!login|reset-password|api|_next/static|_next/image|favicon.ico|sw.js|manifest.webmanifest|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|svg|gif|webp|ico|webmanifest)$).*)",
  ],
};
