"use server";

/**
 * Server actions do RAG Sandbox — Sprint S.1.
 * Aprovar/rejeitar sugestões + bulk approval.
 */

import { revalidatePath } from "next/cache";

import {
  approveRagSuggestion,
  rejectRagSuggestion,
} from "@/lib/api";

type Result =
  | { ok: true; docId?: number }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function approveSuggestionAction(
  id: number
): Promise<Result> {
  try {
    const r = await approveRagSuggestion(id);
    revalidatePath("/dashboard/rag/sandbox");
    return { ok: true, docId: r.doc_id };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function rejectSuggestionAction(
  id: number
): Promise<Result> {
  try {
    await rejectRagSuggestion(id);
    revalidatePath("/dashboard/rag/sandbox");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function bulkApproveAction(
  ids: number[]
): Promise<{ success: number; failed: number; errors: string[] }> {
  const errors: string[] = [];
  let success = 0;
  let failed = 0;
  for (const id of ids) {
    try {
      await approveRagSuggestion(id);
      success += 1;
    } catch (e) {
      failed += 1;
      errors.push(`#${id}: ${toError(e)}`);
    }
  }
  revalidatePath("/dashboard/rag/sandbox");
  return { success, failed, errors };
}

// Sprint S.4 — Upload de dataset JSONL/CSV
type ImportResult =
  | {
      ok: true;
      received: number;
      inserted_fewshot: number;
      inserted_querylog: number;
      skipped: number;
      errors: string[];
    }
  | { ok: false; error: string };

// Sprint T.3 — Sync dataset pro LangSmith
type LangsmithSyncResult =
  | {
      ok: true;
      dataset_id: string;
      dataset_url: string;
      total_db: number;
      already_synced: number;
      created: number;
      errors: string[];
    }
  | { ok: false; error: string };

export async function syncLangsmithAction(
  filterSuccess: boolean
): Promise<LangsmithSyncResult> {
  try {
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    const { headers: nh } = await import("next/headers");
    const reqHeaders = await nh();
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: reqHeaders });
    if (!session?.user?.id) return { ok: false, error: "Sem sessão." };

    const params = new URLSearchParams({
      empresa_id: "999",
      filter_success: String(filterSuccess),
    });
    const r = await fetch(
      `${apiUrl}/api/admin/rag/langsmith/sync?${params}`,
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
    return {
      ok: true,
      dataset_id: data.dataset_id,
      dataset_url: data.dataset_url,
      total_db: data.total_db,
      already_synced: data.already_synced,
      created: data.created,
      errors: data.errors || [],
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// Sprint S.5 — Limpeza dataset (preview + apply)
type CleanResult =
  | {
      ok: true;
      total: number;
      greetings: number;
      low_value: number;
      duplicates: number;
      will_disable: number;
      applied: boolean;
    }
  | { ok: false; error: string };

async function _callClean(dryRun: boolean): Promise<CleanResult> {
  try {
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    const { headers: nh } = await import("next/headers");
    const reqHeaders = await nh();
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: reqHeaders });
    if (!session?.user?.id) return { ok: false, error: "Sem sessão." };

    const r = await fetch(
      `${apiUrl}/api/admin/rag/sandbox/clean?empresa_id=999&dry_run=${dryRun}`,
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
    if (!dryRun) revalidatePath("/dashboard/rag/sandbox");
    return {
      ok: true,
      total: data.total,
      greetings: data.greetings,
      low_value: data.low_value,
      duplicates: data.duplicates,
      will_disable: data.will_disable,
      applied: data.applied,
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function previewCleanAction(): Promise<CleanResult> {
  return _callClean(true);
}

export async function applyCleanAction(): Promise<CleanResult> {
  return _callClean(false);
}

export async function importDatasetAction(
  formData: FormData
): Promise<ImportResult> {
  const file = formData.get("arquivo") as File | null;
  if (!file || file.size === 0) {
    return { ok: false, error: "Arquivo vazio." };
  }
  try {
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    const { headers: nh } = await import("next/headers");
    const reqHeaders = await nh();
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: reqHeaders });
    if (!session?.user?.id) return { ok: false, error: "Sem sessão." };

    const fwd = new FormData();
    fwd.set("file", file, file.name);

    const r = await fetch(`${apiUrl}/api/admin/rag/dataset/import`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "X-User-Id": session.user.id,
      },
      body: fwd,
    });
    if (!r.ok) {
      const txt = await r.text();
      return { ok: false, error: `${r.status}: ${txt.slice(0, 300)}` };
    }
    const data = await r.json();
    revalidatePath("/dashboard/rag/sandbox");
    return {
      ok: true,
      received: data.received ?? 0,
      inserted_fewshot: data.inserted_fewshot ?? 0,
      inserted_querylog: data.inserted_querylog ?? 0,
      skipped: data.skipped ?? 0,
      errors: data.errors ?? [],
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
