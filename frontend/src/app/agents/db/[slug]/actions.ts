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
