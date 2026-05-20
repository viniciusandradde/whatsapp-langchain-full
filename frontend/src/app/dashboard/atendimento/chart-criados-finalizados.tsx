"use client";

import type { ChartCriadosFinalizadosPoint } from "@/lib/dashboard-atendimento-api";

/**
 * Bar chart SVG simples (sem dep externa) — criados vs finalizados por dia.
 */
export function ChartCriadosFinalizados({
  data,
}: {
  data: ChartCriadosFinalizadosPoint[];
}) {
  if (!data.length) {
    return (
      <ChartFrame title="Criados vs Finalizados">
        <EmptyChart text="Sem dados no período" />
      </ChartFrame>
    );
  }

  const maxVal = Math.max(
    1,
    ...data.flatMap((d) => [d.criados, d.finalizados])
  );
  const W = 520;
  const H = 200;
  const padL = 35;
  const padR = 10;
  const padT = 10;
  const padB = 30;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const groupW = innerW / data.length;
  const barW = Math.min(20, groupW / 2 - 2);

  return (
    <ChartFrame
      title="Criados vs Finalizados"
      legend={
        <>
          <Legend color="bg-blue-400" label="Criados" />
          <Legend color="bg-emerald-400" label="Finalizados" />
        </>
      }
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Eixo Y — 4 ticks */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = padT + innerH * (1 - t);
          return (
            <g key={t}>
              <line
                x1={padL}
                x2={W - padR}
                y1={y}
                y2={y}
                stroke="currentColor"
                strokeOpacity="0.08"
              />
              <text
                x={padL - 5}
                y={y + 3}
                fontSize="9"
                textAnchor="end"
                fill="currentColor"
                opacity="0.5"
              >
                {Math.round(maxVal * t)}
              </text>
            </g>
          );
        })}

        {/* Barras */}
        {data.map((d, i) => {
          const xBase = padL + i * groupW + groupW / 2;
          const xCriados = xBase - barW - 1;
          const xFinal = xBase + 1;
          const hCriados = (d.criados / maxVal) * innerH;
          const hFinal = (d.finalizados / maxVal) * innerH;
          const dia = d.dia
            ? new Date(d.dia).toLocaleDateString("pt-BR", {
                day: "2-digit",
                month: "2-digit",
              })
            : "";
          return (
            <g key={d.dia}>
              <rect
                x={xCriados}
                y={padT + innerH - hCriados}
                width={barW}
                height={hCriados}
                fill="rgb(96, 165, 250)"
                rx="2"
              >
                <title>{`Criados ${dia}: ${d.criados}`}</title>
              </rect>
              <rect
                x={xFinal}
                y={padT + innerH - hFinal}
                width={barW}
                height={hFinal}
                fill="rgb(52, 211, 153)"
                rx="2"
              >
                <title>{`Finalizados ${dia}: ${d.finalizados}`}</title>
              </rect>
              <text
                x={xBase}
                y={H - padB + 12}
                fontSize="9"
                textAnchor="middle"
                fill="currentColor"
                opacity="0.6"
              >
                {dia}
              </text>
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

function ChartFrame({
  title,
  children,
  legend,
}: {
  title: string;
  children: React.ReactNode;
  legend?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/40 bg-card/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
        {legend && <div className="flex items-center gap-3 text-[11px]">{legend}</div>}
      </div>
      {children}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block size-2.5 rounded-sm ${color}`} />
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}

function EmptyChart({ text }: { text: string }) {
  return (
    <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">
      {text}
    </div>
  );
}
