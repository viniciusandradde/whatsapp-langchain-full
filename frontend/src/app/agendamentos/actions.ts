"use server";

import { getAgendamentoHistorico, type AgendamentoHistorico } from "@/lib/api";

type Result =
  | { ok: true; items: AgendamentoHistorico[] }
  | { ok: false; error: string };

export async function loadHistoricoAction(id: number): Promise<Result> {
  try {
    const r = await getAgendamentoHistorico(id);
    return { ok: true, items: r.items };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar histórico.",
    };
  }
}
