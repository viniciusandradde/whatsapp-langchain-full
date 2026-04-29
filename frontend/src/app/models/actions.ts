"use server";

import { revalidatePath } from "next/cache";

import { updateAgentConfig } from "@/lib/api";

/**
 * Server Action: persiste o override de modelos pra um agente.
 *
 * Strings vazias viram NULL no DB (volta a usar env). O revalidatePath
 * garante que a próxima navegação até /models traga os valores frescos.
 */
export async function saveAgentConfig(
  agentId: string,
  formData: FormData
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await updateAgentConfig(agentId, {
      chat_model: (formData.get("chat_model") as string) || null,
      midia_model: (formData.get("midia_model") as string) || null,
    });
    revalidatePath("/models");
    return { ok: true };
  } catch (e) {
    const error =
      e instanceof Error ? e.message : "Erro desconhecido ao salvar.";
    return { ok: false, error };
  }
}
