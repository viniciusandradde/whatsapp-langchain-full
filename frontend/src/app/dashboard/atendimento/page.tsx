import { Activity } from "lucide-react";

import { requireSession } from "@/lib/session";
import { getDashboardAtendimento } from "@/lib/dashboard-atendimento-api";

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
    initialData = await getDashboardAtendimento("hoje");
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar dashboard.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-6 w-6" />
          <h1 className="text-2xl font-semibold">Atendimentos — Visão Geral</h1>
        </div>
      </div>

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
