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

// ============== Sprint S.2 — Upload .md/.pdf/.docx ==============

type UploadResult =
  | { ok: true; docs_created: number; doc_ids: number[]; filename: string }
  | { ok: false; error: string; filename: string };

// Sprint S.3 — Re-cluster on-demand (dispara learner empresa 999)
type LearnerResult =
  | { ok: true; misses: number; clusters: number; suggestions_created: number }
  | { ok: false; error: string };

export async function triggerLearnerAction(): Promise<LearnerResult> {
  try {
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    const { headers: nh } = await import("next/headers");
    const reqHeaders = await nh();
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: reqHeaders });
    if (!session?.user?.id) return { ok: false, error: "Sem sessão." };

    const r = await fetch(
      `${apiUrl}/api/admin/rag/learner/run?days=90`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "X-User-Id": session.user.id,
        },
      }
    );
    if (!r.ok) {
      const txt = await r.text();
      return { ok: false, error: `${r.status}: ${txt.slice(0, 300)}` };
    }
    const data = await r.json();
    revalidatePath("/dashboard/rag/sandbox");
    return {
      ok: true,
      misses: data.misses ?? 0,
      clusters: data.clusters ?? 0,
      suggestions_created: data.suggestions_created ?? 0,
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function uploadFileToFolderAction(
  pastaId: number | null,
  formData: FormData
): Promise<UploadResult> {
  const file = formData.get("arquivo") as File | null;
  const filename = file?.name || "(sem nome)";
  if (!file || file.size === 0) {
    return { ok: false, error: "Arquivo vazio.", filename };
  }
  try {
    // Forwarda multipart pro endpoint backend /api/base-conhecimento/upload
    // via fetch direto (apiFetch só suporta JSON body)
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    const { headers: nh } = await import("next/headers");
    const reqHeaders = await nh();
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: reqHeaders });
    if (!session?.user?.id) {
      return { ok: false, error: "Sem sessão.", filename };
    }

    // Re-monta FormData (Next forwards file refs)
    const fwd = new FormData();
    fwd.set("arquivo", file, filename);
    if (pastaId) fwd.set("pasta_id", String(pastaId));
    fwd.set("split_md_headers", "true");

    const r = await fetch(`${apiUrl}/api/base-conhecimento/upload`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "X-User-Id": session.user.id,
      },
      body: fwd,
    });
    if (!r.ok) {
      const txt = await r.text();
      return {
        ok: false,
        error: `${r.status}: ${txt.slice(0, 300)}`,
        filename,
      };
    }
    const data = (await r.json()) as { docs_created: number; doc_ids: number[] };
    revalidatePath("/settings/pastas");
    return {
      ok: true,
      docs_created: data.docs_created,
      doc_ids: data.doc_ids,
      filename,
    };
  } catch (e) {
    return { ok: false, error: toError(e), filename };
  }
}
