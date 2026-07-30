import { NextRequest, NextResponse } from "next/server";
import { cookies, headers } from "next/headers";

import { auth } from "@/lib/auth";

/**
 * Proxy de mídia: `<img src>` do navegador → FastAPI `/mensagens/{id}/midia`.
 *
 * **Por que existe.** A mídia é guardada como data-URL base64 na própria linha
 * de `message_queue`, e o painel recebia tudo embutido na lista de mensagens.
 * Medido em produção no atendimento 466: `/mensagens?limit=50` devolvia
 * **98,74 MB em 2,65s**. O app já resolveu isso pedindo `incluir_midia=false` e
 * buscando cada mídia sob demanda — mas o navegador não conseguia fazer o mesmo,
 * porque `<img src>` e `<audio src>` não mandam header `Authorization`. Foi
 * exatamente por isso que o data-URL existia.
 *
 * Este proxy fecha a lacuna: autentica pelo cookie do Better Auth (que o browser
 * manda sozinho) e injeta o service token + identidade que o backend espera.
 *
 * `Cache-Control: private` porque é conteúdo de um cliente específico — pode
 * ficar no cache do navegador, nunca num cache compartilhado. `immutable` é
 * honesto: mídia de mensagem não muda depois de recebida.
 */
const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ atendimentoId: string; mensagemId: string }> }
): Promise<Response> {
  const { atendimentoId, mensagemId } = await context.params;
  const lado = request.nextUrl.searchParams.get("lado") === "out" ? "out" : "in";

  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Sessão expirada." }, { status: 401 });
    }
    const empresaId = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;

    const r = await fetch(
      `${apiUrl()}/api/atendimentos/${Number(atendimentoId)}` +
        `/mensagens/${Number(mensagemId)}/midia?lado=${lado}`,
      {
        headers: {
          Authorization: `Bearer ${internalToken()}`,
          "X-User-Id": session.user.id,
          ...(empresaId ? { "X-Empresa-Id": empresaId } : {}),
        },
      }
    );
    if (!r.ok) {
      // Sem corpo de erro: quem consome é uma tag <img>, que só olha o status.
      return new NextResponse(null, { status: r.status });
    }

    // Stream direto, sem materializar na memória do Next — um PDF de 5 MB
    // atravessa sem virar Buffer.
    return new NextResponse(r.body, {
      status: 200,
      headers: {
        "Content-Type": r.headers.get("content-type") ?? "application/octet-stream",
        "Cache-Control": "private, max-age=86400, immutable",
      },
    });
  } catch (e) {
    console.error("[proxy midia]", e);
    return new NextResponse(null, { status: 500 });
  }
}
