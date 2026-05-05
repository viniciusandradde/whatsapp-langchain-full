"use server";

import { revalidatePath } from "next/cache";

import {
  createPasta,
  deletePasta,
  updatePasta,
  type Pasta,
  type PastaInput,
} from "@/lib/api";

type SaveResult = { ok: true; pasta: Pasta } | { ok: false; error: string };
type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

function parseParentId(raw: FormDataEntryValue | null): number | null {
  const s = String(raw || "").trim();
  if (!s || s === "0") return null;
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export async function savePastaAction(
  formData: FormData
): Promise<SaveResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const input: PastaInput = {
      nome: String(formData.get("nome") || "").trim(),
      descricao:
        (String(formData.get("descricao") || "").trim() || null) as
          | string
          | null,
      parent_id: parseParentId(formData.get("parent_id")),
    };
    if (!input.nome) return { ok: false, error: "Nome é obrigatório." };
    const pasta = idRaw
      ? await updatePasta(Number(idRaw), input)
      : await createPasta(input);
    revalidatePath("/settings/pastas");
    return { ok: true, pasta };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deletePastaAction(id: number): Promise<Result> {
  try {
    await deletePasta(id);
    revalidatePath("/settings/pastas");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
