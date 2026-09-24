import { NextRequest } from "next/server";

import { proxyClientesExport } from "@/lib/api";
import { requireSession } from "@/lib/session";

/**
 * Download do CSV de clientes. A página aponta um link para cá com os mesmos
 * filtros da lista (`?search=&lifecycle_stage=&temperatura=`); os bytes vêm
 * do backend com o service token, que nunca chega ao navegador.
 */
export async function GET(req: NextRequest) {
  await requireSession();
  try {
    const { bytes, filename } = await proxyClientesExport(req.nextUrl.search);
    return new Response(bytes, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    console.error("[clientes-exportar]", e);
    const msg = e instanceof Error ? e.message : "Não foi possível exportar. Tente novamente.";
    return new Response(msg, { status: 502 });
  }
}
