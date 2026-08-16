import { NextRequest, NextResponse } from "next/server";
import { cookies, headers } from "next/headers";

import { auth } from "@/lib/auth";

/**
 * Leituras do modal "Nova conversa" (conexão padrão + busca de clientes).
 *
 * **Por que não é Server Action.** Toda Server Action faz o Next re-renderizar
 * a árvore RSC da rota atual — em `/atendimento` isso significa refazer a
 * consulta da lista inteira. Medido com Playwright: abrir o modal disparava
 * uma navegação do frame principal, e o autocomplete repetia isso a cada
 * tecla (debounce de 300ms). A tela "piscava como se recarregasse".
 *
 * Leitura não muda nada — então vai por route handler, autenticando pelo
 * cookie do Better Auth e injetando o service token, como o proxy de mídia.
 */
const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function GET(request: NextRequest): Promise<Response> {
  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Sessão expirada." }, { status: 401 });
    }
    const empresaId = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;
    const h = {
      Authorization: `Bearer ${internalToken()}`,
      "X-User-Id": session.user.id,
      ...(empresaId ? { "X-Empresa-Id": empresaId } : {}),
    };
    const q = (request.nextUrl.searchParams.get("q") ?? "").trim();

    // Busca de cliente: só quando o operador digitou algo que vale procurar.
    if (q) {
      const r = await fetch(
        `${apiUrl()}/api/clientes?search=${encodeURIComponent(q)}&limit=5`,
        { headers: h }
      );
      const data = r.ok ? await r.json() : { clientes: [] };
      return NextResponse.json({
        clientes: (data.clientes ?? []).map(
          (c: { id: number; nome: string | null; telefone: string }) => ({
            id: c.id,
            nome: c.nome,
            telefone: c.telefone,
          })
        ),
      });
    }

    // Abertura do modal: só o provider da conexão padrão importa (define se a
    // primeira mensagem é texto livre ou template). A API já ordena com
    // `is_default` na frente.
    const r = await fetch(`${apiUrl()}/api/conexoes`, { headers: h });
    const data = r.ok ? await r.json() : { conexoes: [] };
    const ativas = (data.conexoes ?? []).filter(
      (c: { status?: string }) => c.status === "active"
    );
    return NextResponse.json({ conexao: ativas[0] ?? null });
  } catch (e) {
    console.error("[nova-conversa/opcoes]", e);
    return NextResponse.json({ error: "Falha ao carregar." }, { status: 500 });
  }
}
