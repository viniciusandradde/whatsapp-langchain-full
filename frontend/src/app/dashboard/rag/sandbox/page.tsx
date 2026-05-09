/**
 * Dashboard Sandbox RAG (Sprint R.6).
 *
 * Visualiza dados importados pra empresa 999 (sandbox de análise dos
 * 3 meses do Mackenzie Hospital Evangélico de Dourados).
 *
 * Tem 3 seções:
 * 1. KPIs gerais (total atendimentos, by setor, by outcome)
 * 2. Top problems por setor (clusters criados via R.4)
 * 3. Sugestões pendentes pra aprovação (cria documento_conhecimento)
 */

import { BarChart3, FlaskConical } from "lucide-react";

import {
  getSandboxSummary,
  getSandboxTopProblems,
  type SandboxSummary,
  type SandboxTopProblem as TopProblem,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function loadSandboxSummary(): Promise<SandboxSummary | null> {
  try {
    return await getSandboxSummary(999);
  } catch {
    return null;
  }
}

async function loadTopProblems(): Promise<TopProblem[]> {
  try {
    return await getSandboxTopProblems({ empresaId: 999, limit: 40 });
  } catch {
    return [];
  }
}

export default async function SandboxPage() {
  await requireSession();

  const [summary, topProblems] = await Promise.all([
    loadSandboxSummary(),
    loadTopProblems(),
  ]);

  const setorCounts = summary?.by_setor || {};
  const outcomeCounts = summary?.by_outcome || {};

  // Agrupar top-problems por setor
  const byPasta = new Map<string, TopProblem[]>();
  for (const p of topProblems) {
    const arr = byPasta.get(p.setor) || [];
    arr.push(p);
    byPasta.set(p.setor, arr);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-500">
          <FlaskConical className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">RAG Sandbox</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Análise de 3 meses do Mackenzie Hospital Evangélico de Dourados
            (empresa 999, isolada do prod).
          </p>
        </div>
      </div>

      {/* KPIs */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiCard
            label="Total atendimentos"
            value={summary.total_atendimentos.toLocaleString()}
            hint="fewshot_example empresa=999"
          />
          <KpiCard
            label="Setores classificados"
            value={Object.keys(setorCounts).length}
            hint="sub-categorias hospitalares"
          />
          <KpiCard
            label="Outcomes únicos"
            value={Object.keys(outcomeCounts).length}
            hint="success/transferred/escalated"
          />
          <KpiCard
            label="Sugestões pendentes"
            value={topProblems.length}
            hint="docs gerados via cluster"
          />
        </div>
      )}

      {/* Distribuição por setor */}
      <div className="rounded-lg border bg-muted/20 p-4">
        <div className="mb-3 flex items-center gap-2">
          <BarChart3 className="size-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Distribuição por sub-setor</h2>
        </div>
        <div className="space-y-1.5">
          {Object.entries(setorCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([setor, n]) => {
              const pct = summary ? (n * 100) / summary.total_atendimentos : 0;
              return (
                <div key={setor} className="flex items-center gap-3 text-sm">
                  <span className="w-44 shrink-0 truncate font-mono text-xs">
                    {setor}
                  </span>
                  <div className="flex-1 overflow-hidden rounded bg-background">
                    <div
                      className="h-5 bg-primary/70 transition-all"
                      style={{ width: `${Math.max(pct, 0.5)}%` }}
                    />
                  </div>
                  <span className="w-20 shrink-0 text-right font-mono text-xs text-muted-foreground">
                    {n} ({pct.toFixed(1)}%)
                  </span>
                </div>
              );
            })}
        </div>
      </div>

      {/* Distribuição por outcome */}
      <div className="rounded-lg border bg-muted/20 p-4">
        <h2 className="mb-3 text-sm font-semibold">Distribuição por outcome</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(outcomeCounts).map(([k, v]) => (
            <div
              key={k}
              className="rounded-md border bg-background px-3 py-2 text-sm"
            >
              <p className="text-xs text-muted-foreground">{k}</p>
              <p className="mt-0.5 text-xl font-semibold">{v.toLocaleString()}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Top problems por setor */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">
            Top clusters por sub-setor (sugestões pendentes)
          </h2>
          <span className="text-xs text-muted-foreground">
            Aprovar via /api/admin/rag/suggestions/&lt;id&gt;/approve
          </span>
        </div>
        {byPasta.size === 0 ? (
          <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            Nenhum cluster gerado ainda. Rode{" "}
            <code className="font-mono text-xs">scripts/cluster_hospitalar.py</code>.
          </p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {Array.from(byPasta.entries()).map(([setor, problems]) => (
              <div key={setor} className="rounded-lg border bg-muted/10 p-3">
                <h3 className="mb-2 text-sm font-semibold capitalize">
                  {setor}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    ({problems.length} clusters)
                  </span>
                </h3>
                <ul className="space-y-1.5">
                  {problems.slice(0, 10).map((p, i) => (
                    <li
                      key={i}
                      className="rounded border bg-background px-2 py-1.5 text-xs"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-medium">{p.titulo}</span>
                        <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                          {p.cluster_size}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-1 text-muted-foreground">
                        ↳ {p.sample_query}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p>
    </div>
  );
}
