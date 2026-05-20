"use client";

import type { ChartPorDepartamentoPoint } from "@/lib/dashboard-atendimento-api";

const COLORS = [
  "rgb(96, 165, 250)",   // blue
  "rgb(52, 211, 153)",   // emerald
  "rgb(251, 191, 36)",   // amber
  "rgb(244, 114, 182)",  // pink
  "rgb(168, 85, 247)",   // violet
  "rgb(248, 113, 113)",  // rose
  "rgb(34, 211, 238)",   // cyan
  "rgb(163, 230, 53)",   // lime
];

/**
 * Pizza chart SVG — distribuição por departamento.
 */
export function ChartPorDepartamento({
  data,
}: {
  data: ChartPorDepartamentoPoint[];
}) {
  if (!data.length || data.every((d) => d.total === 0)) {
    return (
      <div className="rounded-lg border border-border/40 bg-card/40 p-4">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Por departamento
        </h3>
        <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">
          Sem dados no período
        </div>
      </div>
    );
  }

  const total = data.reduce((s, d) => s + d.total, 0);
  const cx = 80;
  const cy = 80;
  const r = 70;
  let cumAngle = -Math.PI / 2; // começa no topo

  const arcs = data.map((d, i) => {
    const pct = d.total / total;
    const angle = pct * 2 * Math.PI;
    const x1 = cx + r * Math.cos(cumAngle);
    const y1 = cy + r * Math.sin(cumAngle);
    cumAngle += angle;
    const x2 = cx + r * Math.cos(cumAngle);
    const y2 = cy + r * Math.sin(cumAngle);
    const largeArc = angle > Math.PI ? 1 : 0;
    const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
    return {
      path,
      color: COLORS[i % COLORS.length],
      label: d.departamento,
      total: d.total,
      pct: pct * 100,
    };
  });

  return (
    <div className="rounded-lg border border-border/40 bg-card/40 p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Por departamento
      </h3>
      <div className="flex flex-col items-center gap-4 md:flex-row md:items-start">
        <svg viewBox="0 0 160 160" className="size-40 shrink-0">
          {arcs.map((a, i) => (
            <path key={i} d={a.path} fill={a.color} stroke="rgb(15 15 15)" strokeWidth="1">
              <title>{`${a.label}: ${a.total} (${a.pct.toFixed(1)}%)`}</title>
            </path>
          ))}
        </svg>
        <ul className="flex-1 space-y-1.5 text-xs">
          {arcs.map((a, i) => (
            <li key={i} className="flex items-center gap-2">
              <span
                className="inline-block size-3 shrink-0 rounded-sm"
                style={{ backgroundColor: a.color }}
              />
              <span className="flex-1 truncate" title={a.label}>
                {a.label}
              </span>
              <span className="font-mono text-muted-foreground">
                {a.total} ({a.pct.toFixed(0)}%)
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
