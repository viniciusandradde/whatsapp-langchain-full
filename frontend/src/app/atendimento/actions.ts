"use server";

import { revalidatePath } from "next/cache";

import {
  claimAtendimento,
  closeAtendimento,
  transferAtendimento,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
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
