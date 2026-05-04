"use server";

import { revalidatePath } from "next/cache";

import { updateCalendarRegras } from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

export async function saveCalendarRegrasAction(body: {
  hora_inicio?: string;
  hora_fim?: string;
  antecedencia_minima_minutos?: number;
  intervalo_entre_minutos?: number;
  dias_semana_permitidos?: number[];
  dias_bloqueados?: string[];
  requer_aprovacao?: boolean;
}): Promise<Result> {
  try {
    await updateCalendarRegras(body);
    revalidatePath("/settings/calendar-rules");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar regras.",
    };
  }
}
