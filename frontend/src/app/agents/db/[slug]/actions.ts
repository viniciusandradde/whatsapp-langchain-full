"use server";

import { revalidatePath } from "next/cache";

import {
  deleteAgenteIA,
  getPromptVersao,
  getPromptVersoes,
  restaurarPromptVersao,
  setDefaultAgenteIA,
  updateAgenteIA,
  type AgenteIA,
  type AgenteIAUpdateInput,
  type PromptVersao,
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

// ---- Histórico do prompt (mig 158) ----

export async function listarVersoesPromptAction(
  slug: string
): Promise<Result<PromptVersao[]>> {
  try {
    const out = await getPromptVersoes(slug);
    return { ok: true, data: out.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function redigirPromptAction(
  slug: string,
  descricao: string
): Promise<Result<{ prompt: string; avisos: string[] }>> {
  try {
    const { redigirPromptAgente } = await import("@/lib/api");
    return { ok: true, data: await redigirPromptAgente(slug, descricao) };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function getVersaoPromptAction(
  slug: string,
  versao: number
): Promise<Result<PromptVersao & { texto: string }>> {
  try {
    return { ok: true, data: await getPromptVersao(slug, versao) };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function restaurarVersaoPromptAction(
  slug: string,
  versao: number
): Promise<Result<AgenteIA>> {
  try {
    const out = await restaurarPromptVersao(slug, versao);
    revalidatePath(`/agents/db/${slug}`);
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
  mensagem: string,
  modelo?: string | null,
  midia?: { base64: string; tipo: string; nome: string } | null
): Promise<
  | { ok: true; data: import("@/lib/api").TestarAgenteResult }
  | { ok: false; error: string }
> {
  try {
    const { testarAgente } = await import("@/lib/api");
    return {
      ok: true,
      data: await testarAgente(slug, {
        mensagem,
        modelo,
        midia_base64: midia?.base64 ?? null,
        midia_tipo: midia?.tipo ?? null,
        midia_nome: midia?.nome ?? null,
      }),
    };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao testar o agente.",
    };
  }
}

export async function testarBateriaAction(
  slug: string,
  modelos: string[]
): Promise<
  | { ok: true; data: import("@/lib/api").TestarBateriaResult }
  | { ok: false; error: string }
> {
  try {
    const { testarBateriaAgente } = await import("@/lib/api");
    return { ok: true, data: await testarBateriaAgente(slug, modelos) };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao rodar a bateria.",
    };
  }
}

export async function resetarTesteAgenteAction(
  slug: string,
  modelo?: string | null
): Promise<{ ok: boolean }> {
  try {
    const { testarAgente } = await import("@/lib/api");
    await testarAgente(slug, { mensagem: "", resetar: true, modelo });
    return { ok: true };
  } catch {
    return { ok: false };
  }
}

/**
 * Saúde de IA (F2) — pontes do picker de catálogo completo da aba Modelo &
 * Estilo (superadmin). Server actions porque `lib/api` é server-only.
 */
export async function buscarCatalogoCompletoAction(q: string) {
  try {
    const { getOpenRouterModelos } = await import("@/lib/api");
    const r = await getOpenRouterModelos({ q });
    return { ok: true as const, data: r.items };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Falha ao buscar o catálogo.",
    };
  }
}

export async function analiseModeloAction(slug: string) {
  try {
    const { getOpenRouterAnalise } = await import("@/lib/api");
    return { ok: true as const, data: await getOpenRouterAnalise(slug) };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Falha ao analisar o modelo.",
    };
  }
}

// ---- Seletor de modelos (ADR-004) ----

/**
 * Catálogo completo pro seletor. Sem `revalidatePath`: é leitura, e o
 * TanStack Query do componente já cacheia por 10 min (o sync do worker tem o
 * mesmo passo).
 */
export async function carregarCatalogoModelosAction(): Promise<
  Result<import("@/lib/api").ModeloCatalogo[]>
> {
  try {
    const { getCatalogoModelos } = await import("@/lib/api");
    const r = await getCatalogoModelos();
    return { ok: true, data: r.itens };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
