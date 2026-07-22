"use server";

import { revalidatePath } from "next/cache";

import {
  type WhitelistNumero,
  createWhitelistNumero,
  deleteWhitelistNumero,
  getWhitelist,
  updateWhitelistNumero,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function loadWhitelistAction(): Promise<Result<WhitelistNumero[]>> {
  try {
    const { items } = await getWhitelist();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createWhitelistAction(payload: {
  telefone: string;
  nome?: string | null;
}): Promise<Result<WhitelistNumero>> {
  try {
    const data = await createWhitelistNumero(payload);
    revalidatePath("/whitelist");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateWhitelistAction(
  id: number,
  payload: { nome?: string | null }
): Promise<Result<WhitelistNumero>> {
  try {
    const data = await updateWhitelistNumero(id, payload);
    revalidatePath("/whitelist");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteWhitelistAction(id: number): Promise<Result<true>> {
  try {
    await deleteWhitelistNumero(id);
    revalidatePath("/whitelist");
    return { ok: true, data: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
