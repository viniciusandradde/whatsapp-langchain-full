"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { deleteModeloLLM, updateModeloLLM, type ModeloLLMUpdateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function updateModeloAction(
  id: number,
  formData: FormData
): Promise<void> {
  const numOrUndef = (k: string) => {
    const v = String(formData.get(k) || "").trim();
    return v ? Number(v) : undefined;
  };
  const body: ModeloLLMUpdateInput = {
    nome: String(formData.get("nome") || "").trim() || undefined,
    descricao: String(formData.get("descricao") || "").trim() || null,
    custo_input_mtok: numOrUndef("custo_input_mtok"),
    custo_output_mtok: numOrUndef("custo_output_mtok"),
    janela_contexto: numOrUndef("janela_contexto"),
    ativo: formData.get("ativo") === "on",
  };
  try {
    await updateModeloLLM(id, body);
  } catch (e) {
    redirect(
      `/catalog/models/${id}/edit?error=` + encodeURIComponent(toError(e))
    );
  }
  revalidatePath("/catalog/models");
  revalidatePath(`/catalog/models/${id}/edit`);
  redirect("/catalog/models");
}

export async function deleteModeloAction(id: number): Promise<void> {
  try {
    await deleteModeloLLM(id);
  } catch (e) {
    redirect(
      `/catalog/models/${id}/edit?error=` + encodeURIComponent(toError(e))
    );
  }
  revalidatePath("/catalog/models");
  redirect("/catalog/models");
}
