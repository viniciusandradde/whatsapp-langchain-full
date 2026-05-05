"use server";

import { revalidatePath } from "next/cache";

import {
  deleteFeatureFlag,
  upsertFeatureFlag,
  type FeatureFlag,
} from "@/lib/api";

type Result =
  | { ok: true; flag?: FeatureFlag }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function upsertFlagAction(formData: FormData): Promise<Result> {
  try {
    const key = String(formData.get("key") || "").trim();
    if (!key) return { ok: false, error: "key é obrigatório." };
    const valueRaw = String(formData.get("value") || "true").trim();
    let value: unknown;
    try {
      value = JSON.parse(valueRaw);
    } catch {
      // Aceita string nua (admin pode digitar "A" sem aspas)
      value = valueRaw;
    }
    const ativo = formData.get("ativo") === "on";
    const descricao =
      (String(formData.get("descricao") || "").trim() || null) as
        | string
        | null;

    const flag = await upsertFeatureFlag(key, {
      key,
      value,
      descricao,
      ativo,
    });
    revalidatePath("/settings/feature-flags");
    return { ok: true, flag };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteFlagAction(key: string): Promise<Result> {
  try {
    await deleteFeatureFlag(key);
    revalidatePath("/settings/feature-flags");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
