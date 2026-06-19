import { NextResponse } from "next/server";
import { headers } from "next/headers";

import { friendlyError } from "@/lib/api-error-shared";
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
      console.error("[proxy me-status GET]", r.status, r.statusText);
      return NextResponse.json(
        { error: friendlyError(r.status, "") },
        { status: r.status }
      );
    }
    return NextResponse.json(await r.json());
  } catch (e) {
    console.error("[proxy me-status GET]", e);
    return NextResponse.json(
      { error: "Sessão expirada. Faça login novamente." },
      { status: 401 }
    );
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
      console.error("[proxy me-status POST]", r.status, r.statusText, detail.slice(0, 300));
      return NextResponse.json(
        { error: friendlyError(r.status, detail) },
        { status: r.status }
      );
    }
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    console.error("[proxy me-status POST]", e);
    return NextResponse.json(
      { error: "Sessão expirada. Faça login novamente." },
      { status: 401 }
    );
  }
}
