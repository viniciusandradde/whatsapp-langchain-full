/**
 * Página /atendentes — Sprint H.
 *
 * Lista consolidada dos atendentes da empresa: status (online/ausente/
 * pausa/offline), capacidade (count abertos / max), departamentos,
 * perfis. Substitui navegação entre /companies/[id]/members + /settings/
 * perfis + /settings/departamentos pra UX cotidiano.
 */

import { Headphones } from "lucide-react";

import {
  getAtendentesRanking,
  getDepartamentos,
  getEmpresaAtendentes,
  type AtendenteRankingItem,
  type AtendenteStatus,
  type Departamento,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AtendentesList } from "./atendentes-list";
import { RankingCard } from "./ranking-card";

export const dynamic = "force-dynamic";

export default async function AtendentesPage() {
  await requireSession();

  let atendentes: AtendenteStatus[] = [];
  let departamentos: Departamento[] = [];
  let ranking: AtendenteRankingItem[] = [];
  let error: string | null = null;

  try {
    const [a, d, r] = await Promise.all([
      getEmpresaAtendentes(),
      getDepartamentos().catch(() => ({ departamentos: [] })),
      getAtendentesRanking(30).catch(() => ({ items: [], dias: 30 })),
    ]);
    atendentes = a.atendentes;
    departamentos = d.departamentos;
    ranking = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar atendentes.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Headphones className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Atendentes</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Equipe da empresa — status, capacidade, departamentos e perfis.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <AtendentesList atendentes={atendentes} departamentos={departamentos} />

      <RankingCard items={ranking} dias={30} />
    </div>
  );
}
