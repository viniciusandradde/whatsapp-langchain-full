"use server";

import { revalidatePath } from "next/cache";

import {
  createModeloMensagem,
  deleteModeloMensagem,
  updateModeloMensagem,
  type ModeloMensagemInput,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

function parseInput(form: FormData): ModeloMensagemInput {
  return {
    titulo: String(form.get("titulo") || "").trim(),
    conteudo: String(form.get("conteudo") || "").trim(),
    atalho: ((form.get("atalho") as string) || "").trim() || null,
  };
}

export async function saveModelo(
  modeloId: number | null,
  formData: FormData
): Promise<Result> {
  try {
    const input = parseInput(formData);
    if (!input.titulo) return { ok: false, error: "Título é obrigatório." };
    if (!input.conteudo) return { ok: false, error: "Conteúdo é obrigatório." };
    if (modeloId) {
      await updateModeloMensagem(modeloId, input);
    } else {
      await createModeloMensagem(input);
    }
    revalidatePath("/modelos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteModeloAction(modeloId: number): Promise<Result> {
  try {
    await deleteModeloMensagem(modeloId);
    revalidatePath("/modelos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
