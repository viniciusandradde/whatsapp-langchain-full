import { NextResponse } from "next/server";
import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const apiUrl = () =>
  process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";

/**
 * Proxy GET/POST /api/atendentes/me/status — encapsula auth Better Auth
 * + service token. Client envia POST `{status: 'online'|...}` ou GET pra
 * ler.
 */

async function buildHeaders(): Promise<Record<string, string>> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) {
    throw new Error("not_authenticated");
  }
  return {
    Authorization: `Bearer ${internalToken()}`,
    "X-User-Id": session.user.id,
    "Content-Type": "application/json",
  };
}

export async function GET() {
  try {
    const h = await buildHeaders();
    const r = await fetch(`${apiUrl()}/api/atendentes/me/status`, {
      headers: h,
      cache: "no-store",
    });
    if (!r.ok) {
      return NextResponse.json(
        { error: `upstream ${r.status}` },
        { status: r.status }
      );
    }
    return NextResponse.json(await r.json());
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    return NextResponse.json({ error: msg }, { status: 401 });
  }
}

export async function POST(req: Request) {
  try {
    const h = await buildHeaders();
    const body = await req.text();
    const r = await fetch(`${apiUrl()}/api/atendentes/me/status`, {
      method: "POST",
      headers: h,
      body,
    });
    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      return NextResponse.json(
        { error: detail || `upstream ${r.status}` },
        { status: r.status }
      );
    }
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    return NextResponse.json({ error: msg }, { status: 401 });
  }
}
