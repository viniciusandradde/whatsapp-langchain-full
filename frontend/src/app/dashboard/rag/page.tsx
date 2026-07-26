/**
 * Dashboard de qualidade do RAG (Sprint M.7).
 * Métricas de uso da knowledge base + playground de busca.
 */

import { BarChart3 } from "lucide-react";

import {
  getPastas,
  getRagByAgente,
  getRagRecent,
  getRagSummary,
  getRagTopQueries,
  type AgenteStat,
  type Pasta,
  type RAGSummary,
  type RecentQuery,
  type TopQuery,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { RagPlayground } from "./rag-playground";

export const dynamic = "force-dynamic";

function StatusDot({ value }: { value: number }) {
  // 0 = ruim (vermelho), 1 = ótimo (verde) — escala invertida pra miss rate
  const color =
    value > 0.5
      ? "bg-destructive"
      : value > 0.2
        ? "bg-amber-500"
        : "bg-emerald-500";
  return <span className={`inline-block size-2 rounded-full ${color}`} />;
}

export default async function DashboardRAGPage() {
  await requireSession();

  let summary: RAGSummary | null = null;
  let topQueries: TopQuery[] = [];
  let topMisses: TopQuery[] = [];
  let byAgente: AgenteStat[] = [];
  let recent: RecentQuery[] = [];
  let pastas: Pasta[] = [];
  let error: string | null = null;

  try {
    const [s, tq, tm, ba, rec, pas] = await Promise.all([
      getRagSummary(),
      getRagTopQueries({ days: 7, limit: 10 }),
      getRagTopQueries({ days: 7, onlyMiss: true, limit: 10 }),
      getRagByAgente(7),
      getRagRecent({ limit: 30 }),
      getPastas({ comDocs: true }),
    ]);
    summary = s;
    topQueries = tq;
    topMisses = tm;
    byAgente = ba;
    recent = rec;
    pastas = pas.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar dashboard.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <BarChart3 className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Qualidade do RAG</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Métricas de uso da base de conhecimento, queries top, miss rate e
            playground pra testar buscas.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* === KPIs === */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Queries 24h
            </p>
            <p className="mt-1 text-2xl font-semibold">{summary.queries_24h}</p>
            <p className="text-[11px] text-muted-foreground">
              {summary.queries_7d} nos últimos 7d
            </p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground">
              Miss rate 24h <StatusDot value={summary.miss_rate_24h} />
            </p>
            <p className="mt-1 text-2xl font-semibold">
              {(summary.miss_rate_24h * 100).toFixed(1)}%
            </p>
            <p className="text-[11px] text-muted-foreground">
              queries que retornaram 0 hits
            </p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Score médio
            </p>
            <p className="mt-1 text-2xl font-semibold">
              {summary.avg_score_24h !== null
                ? summary.avg_score_24h.toFixed(3)
                : "—"}
            </p>
            <p className="text-[11px] text-muted-foreground">
              cosine top-1 (0=ruim, 1=ótimo)
            </p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Latência
            </p>
            <p className="mt-1 text-2xl font-semibold">
              {summary.avg_duracao_ms_24h !== null
                ? `${Math.round(summary.avg_duracao_ms_24h)}ms`
                : "—"}
            </p>
            <p className="text-[11px] text-muted-foreground">
              média 24h (cosine + rerank)
            </p>
          </div>
        </div>
      )}

      {/* === Playground === */}
      <RagPlayground pastas={pastas} />

      {/* === Stats por agente === */}
      <div className="rounded-lg border">
        <div className="border-b p-3">
          <h2 className="text-sm font-semibold">Por agente (últimos 7d)</h2>
        </div>
        {byAgente.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">
            Sem dados. Os agentes ainda não chamaram a tool de busca.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-normal">Agente</th>
                <th className="px-3 py-2 font-normal">Queries</th>
                <th className="px-3 py-2 font-normal">Miss rate</th>
                <th className="px-3 py-2 font-normal">Score médio</th>
              </tr>
            </thead>
            <tbody>
              {byAgente.map((a) => (
                <tr key={a.agente_slug ?? "null"} className="border-b last:border-0">
                  <td className="px-3 py-2 font-mono text-xs">
                    {a.agente_slug || "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{a.queries}</td>
                  <td className="px-3 py-2">
                    <span className="flex items-center gap-1">
                      <StatusDot value={a.miss_rate} />
                      <span className="font-mono text-xs">
                        {(a.miss_rate * 100).toFixed(1)}%
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {a.avg_score !== null ? a.avg_score.toFixed(3) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* === Top queries + misses lado a lado === */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-lg border">
          <div className="border-b p-3">
            <h2 className="text-sm font-semibold">Top 10 queries (7d)</h2>
            <p className="text-[11px] text-muted-foreground">
              Mais frequentes — bom indicador do que os clientes perguntam.
            </p>
          </div>
          {topQueries.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">Sem queries.</p>
          ) : (
            <ul className="divide-y">
              {topQueries.map((q, i) => (
                <li key={i} className="flex items-start gap-2 p-2 text-sm">
                  <span className="mt-0.5 text-muted-foreground">{q.n}×</span>
                  <span className="flex-1 break-words">{q.query_text}</span>
                  <StatusDot value={q.miss_rate} />
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-amber-300/50">
          <div className="border-b border-amber-300/50 bg-amber-50/30 p-3 dark:bg-amber-950/20">
            <h2 className="text-sm font-semibold">
              Top 10 misses (0 hits, 7d)
            </h2>
            <p className="text-[11px] text-muted-foreground">
              Queries sem resposta — candidatas pra criar novos docs.
            </p>
          </div>
          {topMisses.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              Nenhum miss. Knowledge base cobrindo bem.
            </p>
          ) : (
            <ul className="divide-y">
              {topMisses.map((q, i) => (
                <li key={i} className="flex items-start gap-2 p-2 text-sm">
                  <span className="mt-0.5 text-muted-foreground">{q.n}×</span>
                  <span className="flex-1 break-words">{q.query_text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* === Histórico recente === */}
      <div className="rounded-lg border">
        <div className="border-b p-3">
          <h2 className="text-sm font-semibold">Últimas 30 queries</h2>
        </div>
        {recent.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">Sem queries ainda.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-normal">Quando</th>
                <th className="px-3 py-2 font-normal">Agente</th>
                <th className="px-3 py-2 font-normal">Query</th>
                <th className="px-3 py-2 font-normal">Hits</th>
                <th className="px-3 py-2 font-normal">Score</th>
                <th className="px-3 py-2 font-normal">Lat</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr
                  key={r.id}
                  className={`border-b last:border-0 ${r.hits === 0 ? "bg-amber-50/20 dark:bg-amber-950/10" : ""}`}
                >
                  <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">
                    {new Date(r.created_at).toLocaleString("pt-BR", {
                      hour: "2-digit",
                      minute: "2-digit",
                      day: "2-digit",
                      month: "2-digit",
                    })}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {r.agente_slug || "—"}
                  </td>
                  <td className="max-w-md truncate px-3 py-2">
                    {r.query_text}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{r.hits}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {r.top_score !== null ? r.top_score.toFixed(3) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">
                    {r.duracao_ms !== null ? `${r.duracao_ms}ms` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
