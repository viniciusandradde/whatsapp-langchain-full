"use server";

import { revalidatePath } from "next/cache";

import {
  deleteAgenteIA,
  setDefaultAgenteIA,
  updateAgenteIA,
  type AgenteIA,
  type AgenteIAUpdateInput,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };
type OkResult = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function updateAgenteAction(
  slug: string,
  patch: AgenteIAUpdateInput
): Promise<Result<AgenteIA>> {
  try {
    const out = await updateAgenteIA(slug, patch);
    revalidatePath(`/agents/db/${slug}`);
    revalidatePath(`/agents`);
    return { ok: true, data: out };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function setDefaultAgenteAction(slug: string): Promise<OkResult> {
  try {
    await setDefaultAgenteIA(slug);
    revalidatePath(`/agents`);
    revalidatePath(`/agents/db/${slug}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteAgenteAction(slug: string): Promise<OkResult> {
  try {
    await deleteAgenteIA(slug);
    revalidatePath(`/agents`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function testarAgenteAction(
  slug: string,
  mensagem: string
): Promise<
  | { ok: true; data: import("@/lib/api").TestarAgenteResult }
  | { ok: false; error: string }
> {
  try {
    const { testarAgente } = await import("@/lib/api");
    return { ok: true, data: await testarAgente(slug, { mensagem }) };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao testar o agente.",
    };
  }
}

export async function resetarTesteAgenteAction(
  slug: string
): Promise<{ ok: boolean }> {
  try {
    const { testarAgente } = await import("@/lib/api");
    await testarAgente(slug, { mensagem: "", resetar: true });
    return { ok: true };
  } catch {
    return { ok: false };
  }
}
