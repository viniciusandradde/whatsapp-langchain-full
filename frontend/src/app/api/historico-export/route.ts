import { NextRequest } from "next/server";

import { proxyHistoricoExport } from "@/lib/api";
import { requireSession } from "@/lib/session";

/**
 * Route handler de download do export do histórico. Roda server-side (tem o
 * service token + headers de auth via proxyHistoricoExport), busca os bytes no
 * backend e devolve com Content-Disposition pro browser baixar o arquivo.
 * A página aponta um <a download> pra cá com `?formato=csv|xlsx&<filtros>`.
 */
export async function GET(req: NextRequest) {
  await requireSession();
  try {
    const { bytes, contentType, filename } = await proxyHistoricoExport(
      req.nextUrl.search
    );
    return new Response(bytes, {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao exportar";
    return new Response(msg, { status: 502 });
  }
}
