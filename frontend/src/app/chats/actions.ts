"use server";

import { getHistoricoDetalhe, type HistoricoDetalhe } from "@/lib/api";

/** Carrega o detalhe agregado de um atendimento pro drawer do histórico. */
export async function loadHistoricoDetalheAction(
  id: number
): Promise<
  { ok: true; detalhe: HistoricoDetalhe } | { ok: false; error: string }
> {
  try {
    const detalhe = await getHistoricoDetalhe(id);
    return { ok: true, detalhe };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar detalhe.",
    };
  }
}
