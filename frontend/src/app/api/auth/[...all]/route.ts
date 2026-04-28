/**
 * Catch-all route para o Better Auth.
 *
 * Todas as chamadas de autenticação (login, logout, sessão, etc.)
 * passam por /api/auth/* e são tratadas pelo Better Auth.
 */
import { auth } from "@/lib/auth";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";
import { toNextJsHandler } from "better-auth/next-js";

const handlers = toNextJsHandler(auth);

function isPublicSignUpRequest(request: Request): boolean {
  return new URL(request.url).pathname.includes("/api/auth/sign-up");
}

export async function GET(request: Request) {
  ensureFrontendRuntimeConfig();

  if (isPublicSignUpRequest(request)) {
    return new Response("Not Found", { status: 404 });
  }

  return handlers.GET(request);
}

export async function POST(request: Request) {
  ensureFrontendRuntimeConfig();

  if (isPublicSignUpRequest(request)) {
    return new Response("Not Found", { status: 404 });
  }

  return handlers.POST(request);
}
