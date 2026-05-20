"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  getDashboardAtendimento,
  type DashboardPayload,
  type Periodo,
} from "@/lib/dashboard-atendimento-api";

import { AtendentesSidebar } from "./atendentes-sidebar";
import { ChartCriadosFinalizados } from "./chart-criados-finalizados";
import { ChartPorDepartamento } from "./chart-por-departamento";
import { ChartPorHora } from "./chart-por-hora";
import { KPICards } from "./kpi-cards";
import { TabelaAguardando } from "./tabela-aguardando";
import { TabelaSemResposta } from "./tabela-sem-resposta";

const REFRESH_INTERVAL_MS = 30_000;

const PERIODO_LABEL: Record<Periodo, string> = {
  hoje: "Hoje",
  "7d": "7 dias",
  "30d": "30 dias",
};

export function DashboardClient({ initial }: { initial: DashboardPayload }) {
  const [data, setData] = useState<DashboardPayload>(initial);
  const [periodo, setPeriodo] = useState<Periodo>(initial.periodo);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isPending, startTransition] = useTransition();
  const [lastError, setLastError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  async function load(p: Periodo) {
    try {
      const fresh = await getDashboardAtendimento(p);
      setData(fresh);
      setLastError(null);
    } catch (e) {
      setLastError(e instanceof Error ? e.message : "Erro de rede");
    }
  }

  function handlePeriodoChange(p: Periodo) {
    setPeriodo(p);
    startTransition(() => load(p));
  }

  function handleManualRefresh() {
    startTransition(() => load(periodo));
  }

  useEffect(() => {
    if (!autoRefresh) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(() => {
      void load(periodo);
    }, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, periodo]);

  const updatedDate = new Date(data.updated_at);
  const updatedStr = updatedDate.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <>
      {/* Barra de filtros + status refresh */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/40 bg-card/40 p-3">
        <div className="flex items-center gap-2">
          {(Object.keys(PERIODO_LABEL) as Periodo[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => handlePeriodoChange(p)}
              disabled={isPending}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                periodo === p
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/70"
              }`}
            >
              {PERIODO_LABEL[p]}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="size-3.5"
            />
            <span>Auto-refresh 30s</span>
          </label>
          <span>·</span>
          <span>Última atualização: {updatedStr}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleManualRefresh}
            disabled={isPending}
            className="h-7 gap-1"
          >
            <RefreshCw
              className={`size-3.5 ${isPending ? "animate-spin" : ""}`}
            />
          </Button>
        </div>
      </div>

      {lastError && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-400">
          Aviso: {lastError} (mostrando última atualização válida)
        </div>
      )}

      {/* Layout principal: grid 4 colunas (3 conteúdo + 1 sidebar atendentes) */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {/* Row 1: KPIs */}
          <KPICards kpis={data.kpis} />

          {/* Row 2: Gráficos */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCriadosFinalizados data={data.charts.criados_finalizados} />
            <ChartPorDepartamento data={data.charts.por_departamento} />
          </div>
          <ChartPorHora data={data.charts.por_hora} />

          {/* Row 3: Tabelas */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TabelaAguardando rows={data.tabelas.aguardando} />
            <TabelaSemResposta rows={data.tabelas.em_andamento_sem_resposta} />
          </div>
        </div>

        {/* Sidebar atendentes */}
        <AtendentesSidebar atendentes={data.atendentes} />
      </div>
    </>
  );
}
