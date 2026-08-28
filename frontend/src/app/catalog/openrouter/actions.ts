"use server";

import { revalidatePath } from "next/cache";

type Resultado<T> = { ok: true; data: T } | { ok: false; error: string };

function msg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

/** 202 — dispara o sync em background no servidor. */
export async function sincronizarAction(): Promise<Resultado<{ status: string }>> {
  try {
    const { syncOpenRouter } = await import("@/lib/api");
    const data = await syncOpenRouter();
    revalidatePath("/catalog/openrouter");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível iniciar a sincronização.") };
  }
}

export async function statusAction(): Promise<
  Resultado<import("@/lib/api").OpenRouterStatus>
> {
  try {
    const { getOpenRouterStatus } = await import("@/lib/api");
    return { ok: true, data: await getOpenRouterStatus() };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível consultar o status.") };
  }
}

export async function buscarModelosAction(params: {
  q?: string;
  modalidade?: string;
}): Promise<Resultado<{ items: import("@/lib/api").OpenRouterModelo[] }>> {
  try {
    const { getOpenRouterModelos } = await import("@/lib/api");
    return { ok: true, data: await getOpenRouterModelos(params) };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível buscar modelos.") };
  }
}

export async function promoverAction(
  slug: string,
  tipo: string
): Promise<Resultado<{ id: number }>> {
  try {
    const { promoverModeloOpenRouter } = await import("@/lib/api");
    const m = await promoverModeloOpenRouter(slug, tipo);
    revalidatePath("/catalog/openrouter");
    revalidatePath("/catalog/models");
    return { ok: true, data: { id: m.id } };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível promover o modelo.") };
  }
}
