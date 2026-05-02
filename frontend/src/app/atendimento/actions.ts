"use server";

import { revalidatePath } from "next/cache";

import {
  claimAtendimento,
  closeAtendimento,
  getAtendimentoMensagens,
  transferAtendimento,
  type AtendimentoMensagem,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type MensagensResult =
  | { ok: true; mensagens: AtendimentoMensagem[] }
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
