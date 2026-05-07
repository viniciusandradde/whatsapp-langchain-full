"use server";

import { revalidatePath } from "next/cache";

import { setAtendenteMaxParalelos } from "@/lib/api";

export async function setMaxParalelosAction(
  userId: string,
  maxParalelos: number
): Promise<{ ok: boolean; error?: string }> {
  try {
    await setAtendenteMaxParalelos(userId, maxParalelos);
    revalidatePath("/atendentes");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar capacidade.",
    };
  }
}
