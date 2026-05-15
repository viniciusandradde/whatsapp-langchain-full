"use server";

import { getMyPermissions } from "@/lib/api";

/**
 * Server Action que carrega permissões do user logado pra Client
 * Components (que não podem importar lib/api.ts diretamente).
 */
export async function loadMyPermissionsAction(): Promise<
  | {
      ok: true;
      permissoes: string[];
      perfis: { id: number; nome: string }[];
    }
  | { ok: false; error: string }
> {
  try {
    const r = await getMyPermissions();
    return { ok: true, permissoes: r.permissoes, perfis: r.perfis };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar permissões.",
    };
  }
}
