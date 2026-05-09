/**
 * Proxy pro Allure HTML report (Sprint L) — index.html.
 *
 * Iframe usa essa URL diretamente. Auth Better Auth + service token
 * injetados aqui.
 *
 * Importante: injeta `<base href="...">` no HTML pra forçar resolução
 * relativa dos assets contra `/report/...` (sem isso o browser tentaria
 * carregar `assets/foo.js` no caminho ERRADO porque o iframe src não
 * tem trailing slash).
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () =>
  process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${apiUrl()}/api/admin/tests/runs/${encodeURIComponent(id)}/report`,
    {
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
      },
    }
  );

  if (upstream.status !== 200) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "text/plain" },
    });
  }

  // Injeta <base href> no <head> pra que assets/data/etc sejam resolvidos
  // contra o caminho do report mesmo sem trailing slash no iframe src.
  const html = await upstream.text();
  const baseHref = `/api/proxy/admin-tests/runs/${encodeURIComponent(id)}/report/`;
  const injected = html.replace(
    /<head([^>]*)>/i,
    `<head$1><base href="${baseHref}">`
  );

  return new Response(injected, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  });
}
