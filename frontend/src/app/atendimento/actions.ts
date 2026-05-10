"use server";

import { revalidatePath } from "next/cache";

import {
  claimAtendimento,
  closeAtendimento,
  getAtendimentoMensagens,
  getDepartamentos,
  getModelosMensagem,
  resetAtendimentoThread,
  responderAtendimento,
  transferAtendimento,
  transferAtendimentoParaDepartamento,
  type AtendimentoMensagem,
  type Departamento,
  type ModeloMensagem,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type MensagensResult =
  | { ok: true; mensagens: AtendimentoMensagem[] }
  | { ok: false; error: string };
type ResponderResult =
  | { ok: true; mensagem: AtendimentoMensagem }
  | { ok: false; error: string };
type ModelosResult =
  | { ok: true; modelos: ModeloMensagem[] }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function loadMensagensAction(
  atendimentoId: number
): Promise<MensagensResult> {
  try {
    const data = await getAtendimentoMensagens(atendimentoId);
    return { ok: true, mensagens: data.mensagens };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadModelosAction(): Promise<ModelosResult> {
  try {
    const data = await getModelosMensagem();
    return { ok: true, modelos: data.modelos };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function responderAction(
  atendimentoId: number,
  conteudo: string
): Promise<ResponderResult> {
  const trimmed = conteudo.trim();
  if (!trimmed) return { ok: false, error: "Mensagem vazia." };
  try {
    const data = await responderAtendimento(atendimentoId, trimmed);
    revalidatePath("/atendimento");
    return { ok: true, mensagem: data.mensagem };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function claimAction(atendimentoId: number): Promise<Result> {
  try {
    await claimAtendimento(atendimentoId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function closeAction(
  atendimentoId: number,
  status: "resolvido" | "abandonado" = "resolvido"
): Promise<Result> {
  try {
    await closeAtendimento(atendimentoId, status);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function transferAction(
  atendimentoId: number,
  userId: string
): Promise<Result> {
  try {
    await transferAtendimento(atendimentoId, userId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function transferDepartamentoAction(
  atendimentoId: number,
  departamentoId: number
): Promise<Result> {
  try {
    await transferAtendimentoParaDepartamento(atendimentoId, departamentoId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type DepartamentosResult =
  | { ok: true; departamentos: Departamento[] }
  | { ok: false; error: string };

export async function loadDepartamentosAction(): Promise<DepartamentosResult> {
  try {
    const r = await getDepartamentos();
    return { ok: true, departamentos: r.departamentos.filter((d) => d.ativo) };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type ResetResult =
  | { ok: true; rowsDeleted: number; threadId: string }
  | { ok: false; error: string };

export async function resetThreadAction(
  atendimentoId: number
): Promise<ResetResult> {
  try {
    const r = await resetAtendimentoThread(atendimentoId);
    return { ok: true, rowsDeleted: r.rows_deleted, threadId: r.thread_id };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
