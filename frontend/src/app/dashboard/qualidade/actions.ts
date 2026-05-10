"use server";

import {
  getNPSAvaliacoes,
  type NPSAvaliacoesPage,
} from "@/lib/api";

type Result =
  | { ok: true; data: NPSAvaliacoesPage }
  | { ok: false; error: string };

export async function loadAvaliacoesAction(opts: {
  periodo?: number;
  categoria?: "promotor" | "neutro" | "detrator";
  pagina?: number;
  limit?: number;
}): Promise<Result> {
  try {
    const data = await getNPSAvaliacoes(opts);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro" };
  }
}
