"use server";

import { revalidatePath } from "next/cache";

import {
  createDocumentoConhecimento,
  createPasta,
  deleteDocumentoConhecimento,
  deletePasta,
  moveDocumentoToPasta,
  updateDocumentoConhecimento,
  updatePasta,
  type DocumentoConhecimento,
  type DocumentoConhecimentoInput,
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

// ============== Docs management dentro das pastas (M.6) ==============

type DocResult =
  | { ok: true; doc: DocumentoConhecimento }
  | { ok: false; error: string };

export async function saveDocumentoAction(
  formData: FormData
): Promise<DocResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const pastaIdRaw = String(formData.get("pasta_id") || "").trim();
    const tagsRaw = String(formData.get("tags") || "").trim();
    const input: DocumentoConhecimentoInput = {
      titulo: String(formData.get("titulo") || "").trim(),
      conteudo: String(formData.get("conteudo") || "").trim(),
      ativo: String(formData.get("ativo") || "true") === "true",
      pasta_id:
        pastaIdRaw && pastaIdRaw !== "0" ? Number(pastaIdRaw) : null,
      tags: tagsRaw
        ? tagsRaw.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
    };
    if (!input.titulo) return { ok: false, error: "Título é obrigatório." };
    if (!input.conteudo)
      return { ok: false, error: "Conteúdo é obrigatório." };
    const doc = idRaw
      ? await updateDocumentoConhecimento(Number(idRaw), input)
      : await createDocumentoConhecimento(input);
    revalidatePath("/settings/pastas");
    return { ok: true, doc };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteDocumentoAction(id: number): Promise<Result> {
  try {
    await deleteDocumentoConhecimento(id);
    revalidatePath("/settings/pastas");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function moveDocumentoAction(
  id: number,
  pastaId: number | null
): Promise<Result> {
  try {
    // Endpoint dedicado: POST /api/pastas/{pasta_id}/documentos/{doc_id}
    // pasta_id=0 → raiz (NULL).
    await moveDocumentoToPasta(id, pastaId);
    revalidatePath("/settings/pastas");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
