"use server";

import { revalidatePath } from "next/cache";

import {
  resetAgenteIAConfig,
  updateAgenteIAConfig,
  type AgenteIAConfigInput,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function saveAgenteIAConfigAction(
  agentId: string,
  formData: FormData
): Promise<Result> {
  try {
    const tempRaw = String(formData.get("temperatura") || "").trim();
    const input: AgenteIAConfigInput = {
      system_prompt_override:
        String(formData.get("system_prompt_override") || "") || null,
      temperatura: tempRaw === "" ? null : Number(tempRaw),
      ativo: formData.get("ativo") === "on",
    };
    if (
      input.temperatura !== null &&
      input.temperatura !== undefined &&
      (Number.isNaN(input.temperatura) ||
        input.temperatura < 0 ||
        input.temperatura > 2)
    ) {
      return { ok: false, error: "Temperatura deve estar entre 0 e 2." };
    }
    await updateAgenteIAConfig(agentId, input);
    revalidatePath(`/agents/${agentId}/edit`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function resetAgenteIAConfigAction(
  agentId: string
): Promise<Result> {
  try {
    await resetAgenteIAConfig(agentId);
    revalidatePath(`/agents/${agentId}/edit`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
