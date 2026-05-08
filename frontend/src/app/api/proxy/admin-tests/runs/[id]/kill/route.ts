/**
 * Proxy POST /api/admin/tests/runs/{id}/kill (Sprint L) — SIGTERM no run.
 */

import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${apiUrl()}/api/admin/tests/runs/${encodeURIComponent(id)}/kill`,
    {
      method: "POST",
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
        upstream.headers.get("Content-Type") || "application/json",
    },
  });
}
