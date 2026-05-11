"use server";

import { revalidatePath } from "next/cache";

import { toggleWorkflowActive, updateWorkflow } from "@/lib/api";

export async function updateWorkflowAction(
  workflowId: number,
  body: {
    nome?: string;
    descricao?: string;
    definicao?: Record<string, unknown>;
  }
): Promise<{ ok: boolean; error?: string; versao?: number }> {
  try {
    const updated = await updateWorkflow(workflowId, body);
    revalidatePath(`/workflows/${workflowId}`);
    revalidatePath("/workflows");
    return { ok: true, versao: updated.versao };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar workflow.",
    };
  }
}

export async function toggleWorkflowActiveAction(
  workflowId: number
): Promise<{ ok: boolean; error?: string; ativo?: boolean }> {
  try {
    const r = await toggleWorkflowActive(workflowId);
    revalidatePath(`/workflows/${workflowId}`);
    revalidatePath("/workflows");
    return { ok: true, ativo: r.ativo };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao alternar status.",
    };
  }
}
