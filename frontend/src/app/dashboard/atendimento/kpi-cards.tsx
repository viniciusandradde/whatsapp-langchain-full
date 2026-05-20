"use client";

import {
  Bot,
  CheckCircle2,
  Clock,
  Hourglass,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { KPIs } from "@/lib/dashboard-atendimento-api";

export function KPICards({ kpis }: { kpis: KPIs }) {
  const cards = [
    {
      label: "Aguardando",
      value: kpis.aguardando,
      icon: Hourglass,
      color: "text-amber-400",
      bg: "bg-amber-500/10 border-amber-500/30",
    },
    {
      label: "Em andamento",
      value: kpis.em_andamento,
      icon: Clock,
      color: "text-blue-400",
      bg: "bg-blue-500/10 border-blue-500/30",
    },
    {
      label: "Resolvidos",
      value: kpis.resolvidos,
      icon: CheckCircle2,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10 border-emerald-500/30",
    },
    {
      label: "Abandonados",
      value: kpis.abandonados,
      icon: XCircle,
      color: "text-rose-400",
      bg: "bg-rose-500/10 border-rose-500/30",
    },
    {
      label: "Tempo médio espera",
      value: `${kpis.tempo_medio_espera_min}m`,
      icon: TrendingUp,
      color: "text-zinc-300",
      bg: "bg-zinc-500/10 border-zinc-500/30",
    },
    {
      label: "% Resolvidos pela IA",
      value: `${kpis.taxa_via_ia_pct}%`,
      icon: Bot,
      color: "text-violet-400",
      bg: "bg-violet-500/10 border-violet-500/30",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div
            key={c.label}
            className={cn("rounded-lg border p-3", c.bg)}
          >
            <div className="flex items-center justify-between">
              <Icon className={cn("size-4", c.color)} />
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {c.label}
              </span>
            </div>
            <div className={cn("mt-2 text-2xl font-semibold", c.color)}>
              {c.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}
