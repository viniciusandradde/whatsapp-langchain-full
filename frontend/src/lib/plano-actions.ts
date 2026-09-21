"use server";

import { getPlanoEmpresa, type PlanoEmpresa } from "@/lib/api";

/**
 * Server Action que entrega o plano efetivo de uma empresa a Client
 * Components (ADR-003: nada de `lib/api.ts` no cliente). O `layout.tsx`
 * carrega a empresa ATIVA no servidor; esta action serve as telas que
 * editam OUTRA empresa (`/companies/[id]`, superadmin) e o refresh.
 */
export async function loadPlanoEmpresaAction(
  empresaId: number
): Promise<{ ok: true; plano: PlanoEmpresa } | { ok: false; error: string }> {
  try {
    return { ok: true, plano: await getPlanoEmpresa(empresaId) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro desconhecido" };
  }
}
