import { cookies, headers } from "next/headers";
import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

/**
 * SSE proxy: Next.js API route → FastAPI /api/atendimentos/events.
 *
 * Mesmo desenho do proxy por atendimento (`../atendimento/[id]/route.ts`),
 * sem o id: é o stream da EMPRESA inteira (mig 145), o mesmo que o app
 * Android usa pra manter a lista viva. No web quem consome é a fila
 * (`fila-live.tsx`) — UMA conexão por operador, não uma por conversa.
 *
 * EventSource nativo não permite headers custom (Bearer + X-User-Id); o
 * proxy autentica via cookie Better Auth e injeta os headers do backend.
 */
export const dynamic = "force-dynamic";
export const maxDuration = 600;

const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const SERVICE_TOKEN = process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function GET(request: NextRequest): Promise<Response> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  if (!SERVICE_TOKEN) {
    return new Response("Service token not configured", { status: 500 });
  }

  const upstreamHeaders: Record<string, string> = {
    Authorization: `Bearer ${SERVICE_TOKEN}`,
    "X-User-Id": session.user.id,
    Accept: "text/event-stream",
  };
  const cookieStore = await cookies();
  const empresaId = cookieStore.get(ACTIVE_EMPRESA_COOKIE)?.value;
  if (empresaId) upstreamHeaders["X-Empresa-Id"] = empresaId;

  const upstream = await fetch(`${API_URL}/api/atendimentos/events`, {
    method: "GET",
    headers: upstreamHeaders,
    signal: request.signal,
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    console.error(
      "[sse empresa]",
      upstream.status,
      upstream.statusText,
      text.slice(0, 300)
    );
    return new Response("Não foi possível abrir o stream de eventos.", {
      status: upstream.status,
    });
  }

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
