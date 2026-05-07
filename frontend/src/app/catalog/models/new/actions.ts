"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createModeloLLM, type ModeloLLMCreateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createModeloAction(formData: FormData): Promise<void> {
  const provedor = String(formData.get("provedor") || "").trim();
  const nome = String(formData.get("nome") || "").trim();
  const tipo = String(formData.get("tipo") || "chat").trim() as ModeloLLMCreateInput["tipo"];
  const descricao = String(formData.get("descricao") || "").trim() || null;
  const numOrNull = (k: string) => {
    const v = String(formData.get(k) || "").trim();
    return v ? Number(v) : null;
  };
  if (!provedor || !nome) {
    redirect(
      "/catalog/models/new?error=" +
        encodeURIComponent("Provedor e nome são obrigatórios.")
    );
  }
  let createdId: number | undefined;
  try {
    const created = await createModeloLLM({
      provedor,
      nome,
      tipo,
      descricao,
      custo_input_mtok: numOrNull("custo_input_mtok"),
      custo_output_mtok: numOrNull("custo_output_mtok"),
      janela_contexto: numOrNull("janela_contexto"),
    });
    createdId = created.id;
  } catch (e) {
    redirect("/catalog/models/new?error=" + encodeURIComponent(toError(e)));
  }
  revalidatePath("/catalog/models");
  redirect(`/catalog/models/${createdId!}/edit`);
}
