/**
 * Proxy POST /api/admin/tests/run (Sprint L) — dispara nova bateria.
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function POST(req: Request) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const body = await req.text();

  const upstream = await fetch(`${apiUrl()}/api/admin/tests/run`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${internalToken()}`,
      "X-User-Id": session.user.id,
      "Content-Type": "application/json",
    },
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") || "application/json",
    },
  });
}
