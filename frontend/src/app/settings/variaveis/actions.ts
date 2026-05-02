"use server";

import { revalidatePath } from "next/cache";

import {
  createVariavel,
  deleteVariavel,
  updateVariavel,
  type VariavelAmbiente,
  type VariavelAmbienteInput,
} from "@/lib/api";

type SaveResult =
  | { ok: true; variavel: VariavelAmbiente }
  | { ok: false; error: string };

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

const NOME_REGEX = /^[a-zA-Z][a-zA-Z0-9_]*$/;

export async function saveVariavelAction(
  formData: FormData
): Promise<SaveResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const input: VariavelAmbienteInput = {
      nome: String(formData.get("nome") || "").trim(),
      valor: String(formData.get("valor") || ""),
      descricao:
        (String(formData.get("descricao") || "").trim() || null) as
          | string
          | null,
      ativo: formData.get("ativo") === "on",
    };
    if (!input.nome || !NOME_REGEX.test(input.nome)) {
      return {
        ok: false,
        error:
          "Nome deve começar com letra e conter apenas letras, números e _.",
      };
    }
    const variavel = idRaw
      ? await updateVariavel(Number(idRaw), input)
      : await createVariavel(input);
    revalidatePath("/settings/variaveis");
    return { ok: true, variavel };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteVariavelAction(id: number): Promise<Result> {
  try {
    await deleteVariavel(id);
    revalidatePath("/settings/variaveis");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
