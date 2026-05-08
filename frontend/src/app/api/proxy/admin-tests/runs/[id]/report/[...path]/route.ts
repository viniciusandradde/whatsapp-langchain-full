/**
 * Proxy catch-all pra assets do Allure (CSS/JS/images).
 * O HTML index.html dentro do iframe pede `data/test-cases/...` etc —
 * essa rota intercepta e proxia pro backend.
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () =>
  process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string; path: string[] }> }
) {
  const { id, path } = await params;
  const subPath = (path || []).map(encodeURIComponent).join("/");
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${apiUrl()}/api/admin/tests/runs/${encodeURIComponent(id)}/report/${subPath}`,
    {
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
      },
    }
  );

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") || "application/octet-stream",
      "Cache-Control": upstream.headers.get("Cache-Control") || "no-cache",
    },
  });
}
