import { cookies, headers } from "next/headers";
import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

/**
 * SSE proxy: Next.js API route → FastAPI /api/atendimentos/{id}/events.
 *
 * EventSource nativo do browser não permite headers custom (Bearer +
 * X-User-Id). Esse proxy autentica via cookie Better Auth e injeta os
 * headers que o backend espera, depois faz stream pass-through dos
 * chunks SSE.
 *
 * Sem buffering — `Cache-Control: no-cache, no-transform` + Content-Type
 * correto evita que Vercel/Traefik agreguem chunks.
 */
export const dynamic = "force-dynamic";
// Evita timeout prematuro no Vercel (não estamos lá hoje, mas safety).
export const maxDuration = 600;

const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const SERVICE_TOKEN = process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await context.params;
  const atendimentoId = Number(id);
  if (!Number.isFinite(atendimentoId)) {
    return new Response("Invalid id", { status: 400 });
  }

  // Valida sessão Better Auth
  const session = await auth.api.getSession({
    headers: await headers(),
  });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  if (!SERVICE_TOKEN) {
    return new Response("Service token not configured", { status: 500 });
  }

  // Monta headers pro upstream (FastAPI)
  const upstreamHeaders: Record<string, string> = {
    Authorization: `Bearer ${SERVICE_TOKEN}`,
    "X-User-Id": session.user.id,
    Accept: "text/event-stream",
  };
  const cookieStore = await cookies();
  const empresaId = cookieStore.get(ACTIVE_EMPRESA_COOKIE)?.value;
  if (empresaId) upstreamHeaders["X-Empresa-Id"] = empresaId;

  const upstream = await fetch(
    `${API_URL}/api/atendimentos/${atendimentoId}/events`,
    {
      method: "GET",
      headers: upstreamHeaders,
      // Importante: signal pra encerrar fetch quando client disconectar
      signal: request.signal,
      cache: "no-store",
    }
  );

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "Upstream error");
    return new Response(text, { status: upstream.status });
  }

  // Stream pass-through. Browser recebe os chunks SSE diretamente.
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
