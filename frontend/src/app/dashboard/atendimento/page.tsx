import { Activity } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import { requireSession } from "@/lib/session";

import { fetchDashboardAtendimentoAction } from "./actions";
import { DashboardClient } from "./dashboard-client";

export const dynamic = "force-dynamic";

/**
 * Dashboard Operacional de Atendimento — página inicial do Nexus.
 *
 * Fornece visão completa do dia/semana/mês: KPIs, fila de espera,
 * atendimentos sem resposta, gráficos e atendentes online.
 *
 * Substitui o dashboard antigo do ZigChat com 2x mais informação e
 * auto-refresh.
 */
export default async function DashboardAtendimentoPage() {
  await requireSession();

  let initialData = null;
  let error: string | null = null;
  try {
    initialData = await fetchDashboardAtendimentoAction("hoje");
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar dashboard.";
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Visão geral"
        descricao="O que está acontecendo no atendimento agora."
        icon={Activity}
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar o dashboard</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && initialData && <DashboardClient initial={initialData} />}
    </div>
  );
}
