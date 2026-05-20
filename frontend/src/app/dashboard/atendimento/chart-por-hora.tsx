"use client";

import type { ChartPorHoraPoint } from "@/lib/dashboard-atendimento-api";

/**
 * Heatmap simples — 24 colunas, intensidade pelo total.
 */
export function ChartPorHora({ data }: { data: ChartPorHoraPoint[] }) {
  const maxVal = Math.max(1, ...data.map((d) => d.total));

  function intensity(total: number): string {
    if (total === 0) return "bg-muted/40";
    const ratio = total / maxVal;
    if (ratio < 0.2) return "bg-blue-400/20";
    if (ratio < 0.4) return "bg-blue-400/40";
    if (ratio < 0.6) return "bg-blue-400/60";
    if (ratio < 0.8) return "bg-blue-400/80";
    return "bg-blue-400";
  }

  return (
    <div className="rounded-lg border border-border/40 bg-card/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Atendimentos por hora do dia
        </h3>
        <span className="text-[10px] text-muted-foreground">
          Quanto mais escuro, mais atendimentos
        </span>
      </div>
      <div className="grid grid-cols-12 gap-1 sm:grid-cols-24" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
        {data.map((d) => (
          <div key={d.hora} className="flex flex-col items-center gap-1">
            <div
              className={`h-12 w-full rounded ${intensity(d.total)} transition-colors`}
              title={`${String(d.hora).padStart(2, "0")}h — ${d.total} atendimentos`}
            />
            <span className="text-[9px] text-muted-foreground">
              {String(d.hora).padStart(2, "0")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
