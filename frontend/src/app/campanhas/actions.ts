"use server";

import { revalidatePath } from "next/cache";

import {
  abortCampanha,
  createCampanha,
  dispatchCampanha,
  type Campanha,
  type CampanhaCreateInput,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };
type OkResult = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createCampanhaAction(
  body: CampanhaCreateInput
): Promise<Result<Campanha>> {
  try {
    const c = await createCampanha(body);
    revalidatePath("/campanhas");
    return { ok: true, data: c };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function dispatchCampanhaAction(id: number): Promise<OkResult> {
  try {
    await dispatchCampanha(id);
    revalidatePath("/campanhas");
    revalidatePath(`/campanhas/${id}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function abortCampanhaAction(id: number): Promise<OkResult> {
  try {
    await abortCampanha(id);
    revalidatePath("/campanhas");
    revalidatePath(`/campanhas/${id}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
