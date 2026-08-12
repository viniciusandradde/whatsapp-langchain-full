import { NextRequest } from "next/server";

import { proxyRelatorioUsoPdf } from "@/lib/api";
import { requireSession } from "@/lib/session";

/**
 * Download do PDF do relatório de uso.
 *
 * O `<a>` da tela não pode apontar direto para a FastAPI: o browser não
 * carrega o service token, e `/api/...` no host do painel é o Next, não a API.
 * Aqui roda server-side, com os headers de auth, e devolve os bytes.
 *
 * `inline` e não `attachment`: o operador abre para conferir antes de disparar
 * ao cliente, e o navegador já sabe mostrar PDF.
 */
export async function GET(req: NextRequest) {
  await requireSession();

  const empresaId = Number(req.nextUrl.searchParams.get("empresa_id"));
  const competencia = req.nextUrl.searchParams.get("competencia") || "";
  if (!empresaId || !/^\d{4}-\d{2}$/.test(competencia)) {
    return new Response("Informe empresa_id e competencia no formato AAAA-MM.", {
      status: 400,
    });
  }

  try {
    const { bytes, filename } = await proxyRelatorioUsoPdf(empresaId, competencia);
    return new Response(bytes, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    console.error("[relatorio-uso-pdf]", e);
    return new Response("Não foi possível gerar o PDF. Tente novamente.", {
      status: 502,
    });
  }
}
