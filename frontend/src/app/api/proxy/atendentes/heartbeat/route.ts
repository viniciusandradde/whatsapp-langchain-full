import { NextResponse } from "next/server";
import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () =>
  process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

/**
 * Proxy POST /api/atendentes/me/heartbeat — prova-de-vida do atendente.
 * Cliente envia a cada 60s quando status=online (Sprint G.4).
 */
export async function POST() {
  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "not_authenticated" }, { status: 401 });
    }
    const r = await fetch(`${apiUrl()}/api/atendentes/me/heartbeat`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
      },
    });
    if (!r.ok) {
      return NextResponse.json(
        { error: `upstream ${r.status}` },
        { status: r.status }
      );
    }
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
