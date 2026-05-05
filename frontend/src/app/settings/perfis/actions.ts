"use server";

import { revalidatePath } from "next/cache";

import {
  createPerfil,
  deletePerfil,
  getPerfil,
  updatePerfil,
  type PerfilAcesso,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type PerfilResult =
  | { ok: true; perfil: PerfilAcesso }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function loadPerfilAction(perfilId: number): Promise<PerfilResult> {
  try {
    const perfil = await getPerfil(perfilId);
    return { ok: true, perfil };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createPerfilAction(body: {
  nome: string;
  descricao?: string | null;
  permissoes: string[];
}): Promise<PerfilResult> {
  try {
    const perfil = await createPerfil(body);
    revalidatePath("/settings/perfis");
    return { ok: true, perfil };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updatePerfilAction(
  perfilId: number,
  body: { permissoes: string[]; descricao?: string | null }
): Promise<PerfilResult> {
  try {
    const perfil = await updatePerfil(perfilId, body);
    revalidatePath("/settings/perfis");
    return { ok: true, perfil };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deletePerfilAction(perfilId: number): Promise<Result> {
  try {
    await deletePerfil(perfilId);
    revalidatePath("/settings/perfis");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
