import { NextRequest, NextResponse } from "next/server";
import { cookies, headers } from "next/headers";

import { auth } from "@/lib/auth";

/**
 * Proxy da importação de clientes por CSV → FastAPI `/api/clientes/importar`.
 *
 * Route Handler e não Server Action: o corpo da Server Action é de 1 MB e o
 * CSV aceito vai até 2 MB. Mesmo desenho do proxy de mídia do composer: o
 * FormData é reconstruído (boundary do multipart) e o service token nunca
 * chega ao navegador (ADR-003).
 */
export const dynamic = "force-dynamic";

const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function POST(request: NextRequest): Promise<Response> {
  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Sessão expirada." }, { status: 401 });
    }
    const empresaId = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;

    const entrada = await request.formData();
    const arquivo = entrada.get("arquivo");
    if (!(arquivo instanceof File) || arquivo.size === 0) {
      return NextResponse.json({ error: "Nenhum arquivo enviado." }, { status: 400 });
    }
    const saida = new FormData();
    saida.set("arquivo", arquivo, arquivo.name || "clientes.csv");

    const r = await fetch(`${apiUrl()}/api/clientes/importar`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
        ...(empresaId ? { "X-Empresa-Id": empresaId } : {}),
      },
      body: saida,
    });

    const texto = await r.text();
    if (!r.ok) {
      let detail = "Não foi possível importar o arquivo.";
      try {
        const j = JSON.parse(texto) as { detail?: unknown };
        if (typeof j.detail === "string" && j.detail) detail = j.detail;
      } catch {
        // corpo não JSON: fica a frase genérica
      }
      return NextResponse.json({ error: detail }, { status: r.status });
    }
    return new NextResponse(texto, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("[proxy clientes importar]", e);
    return NextResponse.json(
      { error: "Não foi possível importar o arquivo." },
      { status: 500 }
    );
  }
}
