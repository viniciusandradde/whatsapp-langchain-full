/**
 * Página /atendentes — Sprint H.
 *
 * Lista consolidada dos atendentes da empresa: status (online/ausente/
 * pausa/offline), capacidade (count abertos / max), departamentos,
 * perfis. Substitui navegação entre /companies/[id]/members + /settings/
 * perfis + /settings/departamentos pra UX cotidiano.
 */

import { Headphones } from "lucide-react";

import { PageHeader } from "@/components/page-header";

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
      <PageHeader
        titulo="Atendentes"
        descricao="Equipe da empresa — status, capacidade, departamentos e perfis."
        icon={Headphones}
      />

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
