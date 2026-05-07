"use server";

import { revalidatePath } from "next/cache";

import { upsertIaBudget } from "@/lib/api";

export async function saveBudgetAction(formData: FormData): Promise<{
  ok: boolean;
  error?: string;
}> {
  const limite = Number(formData.get("limite_usd") || "0");
  const acao = String(formData.get("acao_estouro") || "alertar") as
    | "alertar"
    | "bloquear"
    | "redirecionar_menu";
  const alerta = Number(formData.get("alerta_pct") || "80");

  try {
    await upsertIaBudget({
      limite_usd: limite,
      acao_estouro: acao,
      alerta_pct: alerta,
    });
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar budget.",
    };
  }
  revalidatePath("/governanca/ia-budget");
  revalidatePath("/dashboard/ia");
  return { ok: true };
}
