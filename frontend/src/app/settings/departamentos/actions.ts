"use server";

import { revalidatePath } from "next/cache";

import {
  createDepartamento,
  deleteDepartamento,
  updateDepartamento,
  type Departamento,
  type DepartamentoInput,
} from "@/lib/api";

type SaveResult =
  | { ok: true; departamento: Departamento }
  | { ok: false; error: string };

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function saveDepartamentoAction(
  formData: FormData
): Promise<SaveResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const input: DepartamentoInput = {
      nome: String(formData.get("nome") || "").trim(),
      descricao:
        (String(formData.get("descricao") || "").trim() || null) as
          | string
          | null,
      ativo: formData.get("ativo") === "on",
    };
    if (!input.nome) return { ok: false, error: "Nome é obrigatório." };
    const departamento = idRaw
      ? await updateDepartamento(Number(idRaw), input)
      : await createDepartamento(input);
    revalidatePath("/settings/departamentos");
    return { ok: true, departamento };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteDepartamentoAction(
  id: number
): Promise<Result> {
  try {
    await deleteDepartamento(id);
    revalidatePath("/settings/departamentos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
