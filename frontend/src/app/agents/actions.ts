"use server";

import { revalidatePath } from "next/cache";

import { getAgentesIA, updateAgenteIA } from "@/lib/api";

/**
 * Desativa em massa TODOS os agentes IA ativos da empresa. Útil quando
 * admin quer parar atendimentos automatizados pra mudar config sem o
 * worker chamar agentes no meio.
 *
 * Retorna `qtde` de agentes que foram desativados (já-inativos ignorados).
 * Erros individuais não param o batch — coleta lista de slugs falhos.
 */
export async function deactivateAllAgentesAction(): Promise<{
  ok: boolean;
  qtde: number;
  falhas: string[];
  error?: string;
}> {
  try {
    const { items } = await getAgentesIA({ onlyActive: true });
    const ativos = items.filter((a) => a.ativo);
    const falhas: string[] = [];
    let qtde = 0;
    for (const a of ativos) {
      try {
        await updateAgenteIA(a.slug, { ativo: false });
        qtde++;
      } catch (e) {
        falhas.push(`${a.slug} (${e instanceof Error ? e.message : "erro"})`);
      }
    }
    revalidatePath("/agents");
    return { ok: falhas.length === 0, qtde, falhas };
  } catch (e) {
    return {
      ok: false,
      qtde: 0,
      falhas: [],
      error: e instanceof Error ? e.message : "Erro ao listar agentes.",
    };
  }
}
