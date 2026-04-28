import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { getQueue } from "@/lib/api";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

/**
 * Route Handler que faz proxy para a API interna de fila.
 *
 * O Client Component faz polling neste endpoint (a cada 5s),
 * sem expor a URL/token da API FastAPI para o navegador.
 *
 * Valida a sessao do Better Auth antes de retornar dados —
 * sem isso, qualquer cliente sem login conseguiria acessar a fila.
 */
export async function GET() {
  ensureFrontendRuntimeConfig();

  // Valida sessao real (banco), nao apenas cookie
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session) {
    return NextResponse.json({ error: "Nao autenticado" }, { status: 401 });
  }

  try {
    const data = await getQueue();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Erro ao buscar fila";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
