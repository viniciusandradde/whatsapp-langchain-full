"use server";

import { revalidatePath } from "next/cache";

import {
  type CapturaLote,
  type ContatoCapturado,
  type DisparadorApiKey,
  type DisparadorApiKeyCreated,
  type GrupoCapturado,
  capturarViaEvolution,
  createApiKey,
  despromoverContatos,
  getCapturaLote,
  getContatosCapturados,
  getGruposCapturados,
  listApiKeys,
  promoverContatos,
  revokeApiKey,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function listApiKeysAction(): Promise<Result<DisparadorApiKey[]>> {
  try {
    const { items } = await listApiKeys();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createApiKeyAction(
  label: string,
  scopes: string[]
): Promise<Result<DisparadorApiKeyCreated>> {
  try {
    const data = await createApiKey({ label, scopes });
    revalidatePath("/disparador/api-keys");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function revokeApiKeyAction(id: number): Promise<Result<true>> {
  try {
    await revokeApiKey(id);
    revalidatePath("/disparador/api-keys");
    return { ok: true, data: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function listContatosAction(): Promise<Result<ContatoCapturado[]>> {
  try {
    const { items } = await getContatosCapturados();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function listGruposAction(): Promise<Result<GrupoCapturado[]>> {
  try {
    const { items } = await getGruposCapturados();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function promoverContatosAction(
  ids: number[]
): Promise<Result<number>> {
  try {
    const { promovidos } = await promoverContatos(ids);
    revalidatePath("/disparador/contatos");
    return { ok: true, data: promovidos };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function despromoverContatosAction(
  ids: number[]
): Promise<Result<{ removidos: number; mantidos_com_atendimento: number }>> {
  try {
    const data = await despromoverContatos(ids);
    revalidatePath("/disparador/contatos");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function capturarViaEvolutionAction(
  conexaoId: number,
  tipo: "contatos" | "grupos"
): Promise<Result<{ lote_id: number; status: string }>> {
  try {
    const data = await capturarViaEvolution(conexaoId, tipo);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function getCapturaLoteAction(
  loteId: number
): Promise<Result<CapturaLote>> {
  try {
    const data = await getCapturaLote(loteId);
    revalidatePath("/disparador/contatos");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
