"use server";

import { revalidatePath } from "next/cache";

import {
  buscarDocumentosConhecimento,
  createDocumentoConhecimento,
  deleteDocumentoConhecimento,
  resetAgenteIAConfig,
  updateAgenteIAConfig,
  updateDocumentoConhecimento,
  uploadDocumentoConhecimento,
  type AgenteIAConfigInput,
  type BuscarDocumentosResponse,
  type DocumentoConhecimento,
  type DocumentoConhecimentoInput,
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

// --- M5.c Base de Conhecimento ---

type SaveDocumentoResult =
  | { ok: true; documento: DocumentoConhecimento }
  | { ok: false; error: string };

export async function saveDocumentoAction(
  agentId: string,
  formData: FormData
): Promise<SaveDocumentoResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const tagsRaw = String(formData.get("tags") || "").trim();
    const tags = tagsRaw
      ? tagsRaw.split(",").map((t) => t.trim()).filter(Boolean)
      : [];
    const input: DocumentoConhecimentoInput = {
      titulo: String(formData.get("titulo") || "").trim(),
      conteudo: String(formData.get("conteudo") || "").trim(),
      tags,
      ativo: formData.get("ativo") === "on",
    };
    if (!input.titulo || !input.conteudo) {
      return { ok: false, error: "Título e conteúdo são obrigatórios." };
    }
    const documento = idRaw
      ? await updateDocumentoConhecimento(Number(idRaw), input)
      : await createDocumentoConhecimento(input);
    revalidatePath(`/agents/${agentId}/edit`);
    return { ok: true, documento };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteDocumentoAction(
  agentId: string,
  id: number
): Promise<Result> {
  try {
    await deleteDocumentoConhecimento(id);
    revalidatePath(`/agents/${agentId}/edit`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type BuscarResult =
  | { ok: true; data: BuscarDocumentosResponse }
  | { ok: false; error: string };

export async function buscarDocumentosAction(
  query: string
): Promise<BuscarResult> {
  try {
    const data = await buscarDocumentosConhecimento(query);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function uploadDocumentoAction(
  agentId: string,
  formData: FormData
): Promise<SaveDocumentoResult> {
  try {
    const arquivo = formData.get("arquivo");
    if (!(arquivo instanceof File) || !arquivo.size) {
      return { ok: false, error: "Selecione um arquivo." };
    }
    const titulo = String(formData.get("titulo") || "").trim() || undefined;
    const tagsRaw = String(formData.get("tags") || "").trim();
    const tags = tagsRaw
      ? tagsRaw.split(",").map((t) => t.trim()).filter(Boolean)
      : undefined;
    const documento = await uploadDocumentoConhecimento(arquivo, {
      titulo,
      tags,
    });
    revalidatePath(`/agents/${agentId}/edit`);
    return { ok: true, documento };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
