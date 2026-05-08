/**
 * Proxy GET /api/admin/tests/runs (Sprint L) — histórico de runs.
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(`${apiUrl()}/api/admin/tests/runs`, {
    headers: {
      Authorization: `Bearer ${internalToken()}`,
      "X-User-Id": session.user.id,
    },
    cache: "no-store",
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") || "application/json",
    },
  });
}
