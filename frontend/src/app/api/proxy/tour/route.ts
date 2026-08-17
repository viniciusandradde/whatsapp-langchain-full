import { NextResponse } from "next/server";
import { cookies, headers } from "next/headers";

import { auth } from "@/lib/auth";

/**
 * Guia de primeiro acesso: leitura e marcação do estado do próprio usuário.
 *
 * Route handler (não Server Action) porque Server Action re-renderiza a
 * árvore RSC da rota — o guia roda no layout, e isso recarregaria a página
 * do usuário ao abrir e ao concluir.
 */
const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

async function cabecalhos() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.id) return null;
  const empresaId = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;
  return {
    Authorization: `Bearer ${internalToken()}`,
    "X-User-Id": session.user.id,
    ...(empresaId ? { "X-Empresa-Id": empresaId } : {}),
  };
}

export async function GET(): Promise<Response> {
  try {
    const h = await cabecalhos();
    // Sem sessão: responder "visto" evita piscar o guia em tela de login.
    if (!h) return NextResponse.json({ visto: true });
    const r = await fetch(`${apiUrl()}/api/usuarios/me/tour`, { headers: h });
    if (!r.ok) return NextResponse.json({ visto: true });
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ visto: true });
  }
}

export async function POST(): Promise<Response> {
  try {
    const h = await cabecalhos();
    if (!h) return NextResponse.json({ ok: false }, { status: 401 });
    const r = await fetch(`${apiUrl()}/api/usuarios/me/tour`, {
      method: "POST",
      headers: h,
    });
    return NextResponse.json({ ok: r.ok }, { status: r.ok ? 200 : 502 });
  } catch {
    return NextResponse.json({ ok: false }, { status: 502 });
  }
}
