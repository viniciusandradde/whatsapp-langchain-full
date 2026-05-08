/**
 * Proxy SSE pro stream de eventos do test runner (Sprint L).
 * EventSource nativo do browser não envia headers customizados — então
 * o frontend bate aqui, e essa rota injeta auth Better Auth + service
 * token e faz pipe do upstream pro client.
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () =>
  process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${apiUrl()}/api/admin/tests/runs/${encodeURIComponent(id)}/events`,
    {
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
        Accept: "text/event-stream",
      },
      // SSE precisa de stream — Node fetch suporta nativamente
      // @ts-expect-error — Node fetch typing inadequado pra duplex
      duplex: "half",
      signal: request.signal,
    }
  );

  if (!upstream.ok) {
    return new Response(`Upstream ${upstream.status}`, { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
