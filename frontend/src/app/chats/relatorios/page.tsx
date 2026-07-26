import { ArrowLeft, BarChart3 } from "lucide-react";
import Link from "next/link";

import { ApiError } from "@/components/ui/api-error";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getHistoricoPorCanal,
  getHistoricoPorDepartamento,
  getHistoricoPorOperador,
  getHistoricoResumo,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const PERIODOS = [7, 30, 90, 180];

function fmtN(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("pt-BR");
}
function fmtDur(seg: number | null | undefined): string {
  if (seg == null) return "—";
  if (seg < 60) return `${seg}s`;
  const min = Math.round(seg / 60);
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  return `${h}h ${min % 60}min`;
}
function fmtPct(n: number | null | undefined): string {
  return n == null ? "—" : `${n}`;
}
function npsColor(nps: number | null | undefined): string {
  if (nps == null) return "text-muted-foreground";
  if (nps >= 50) return "text-emerald-600 dark:text-emerald-400";
  if (nps >= 0) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

export default async function RelatoriosPage({
  searchParams,
}: {
  searchParams: Promise<{ dias?: string }>;
}) {
  await requireSession();
  const sp = await searchParams;
  const dias = PERIODOS.includes(Number(sp.dias)) ? Number(sp.dias) : 30;

  let resumo: Awaited<ReturnType<typeof getHistoricoResumo>> | null = null;
  let operadores: { nome: string | null; total: number; resolvidos: number; tempo_medio_seg: number | null; csat_medio: number | null }[] = [];
  let deptos: { departamento_nome: string | null; total: number; resolvidos: number; tempo_medio_seg: number | null; csat_medio: number | null }[] = [];
  let canais: { canal: string | null; total: number; resolvidos: number }[] = [];
  let error: string | null = null;

  try {
    const [r, op, dp, cn] = await Promise.all([
      getHistoricoResumo(dias),
      getHistoricoPorOperador(dias),
      getHistoricoPorDepartamento(dias),
      getHistoricoPorCanal(dias),
    ]);
    resumo = r;
    operadores = op.items;
    deptos = dp.items;
    canais = cn.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar relatórios.";
  }

  const k = resumo?.kpis;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3">
        <BarChart3 className="h-6 w-6 text-muted-foreground" />
        <div className="flex-1">
          <h1 className="text-xl font-semibold">Relatórios do Histórico</h1>
          <p className="text-sm text-muted-foreground">
            Volume, tempos, SLA e satisfação por período.
          </p>
        </div>
        <Link
          href="/chats"
          className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-muted"
        >
          <ArrowLeft className="h-4 w-4" /> Histórico
        </Link>
      </header>

      {/* Seletor de período */}
      <div className="flex gap-1">
        {PERIODOS.map((p) => (
          <Link
            key={p}
            href={`/chats/relatorios?dias=${p}`}
            className={`rounded-full border px-3 py-1 text-xs ${
              p === dias
                ? "border-primary bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {p} dias
          </Link>
        ))}
      </div>

      {error && <ApiError error={error} />}

      {k && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Atendimentos" value={fmtN(k.total)} />
            <Kpi
              label="Resolvidos"
              value={fmtN(k.resolvidos)}
              sub={`${fmtN(k.resolvidos_via_ia)} via IA`}
            />
            <Kpi
              label="Tempo médio resolução"
              value={fmtDur(k.tempo_medio_resolucao_seg)}
            />
            <Kpi
              label="Tempo médio 1ª resposta"
              value={fmtDur(k.tempo_medio_primeira_resposta_seg)}
            />
            <Kpi label="Abertos agora" value={fmtN(k.abertos)} />
            <Kpi label="Abandonados" value={fmtN(k.abandonados)} />
            <Kpi
              label="CSAT médio"
              value={k.csat_medio != null ? `${k.csat_medio}/10` : "—"}
              sub={`${fmtN(k.avaliacoes)} avaliações`}
            />
            <Kpi
              label="NPS"
              value={fmtPct(k.nps)}
              valueClass={npsColor(k.nps)}
            />
          </div>

          {/* Tabelas */}
          <div className="grid gap-4 lg:grid-cols-2">
            <TabelaRanking
              titulo="Por operador"
              cols={["Operador", "Total", "Resolv.", "T. médio", "CSAT"]}
              rows={operadores.map((o) => [
                o.nome ?? "—",
                fmtN(o.total),
                fmtN(o.resolvidos),
                fmtDur(o.tempo_medio_seg),
                o.csat_medio != null ? String(o.csat_medio) : "—",
              ])}
            />
            <TabelaRanking
              titulo="Por departamento"
              cols={["Departamento", "Total", "Resolv.", "T. médio", "CSAT"]}
              rows={deptos.map((d) => [
                d.departamento_nome ?? "—",
                fmtN(d.total),
                fmtN(d.resolvidos),
                fmtDur(d.tempo_medio_seg),
                d.csat_medio != null ? String(d.csat_medio) : "—",
              ])}
            />
            <TabelaRanking
              titulo="Por canal"
              cols={["Canal", "Total", "Resolvidos"]}
              rows={canais.map((c) => [
                c.canal ?? "—",
                fmtN(c.total),
                fmtN(c.resolvidos),
              ])}
            />
            <SerieDiaria serie={resumo!.serie_diaria} />
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-normal text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${valueClass ?? ""}`}>{value}</div>
        {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function TabelaRanking({
  titulo,
  cols,
  rows,
}: {
  titulo: string;
  cols: string[];
  rows: string[][];
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              {cols.map((c, i) => (
                <th
                  key={c}
                  className={`px-4 py-2 ${i > 0 ? "text-right" : ""}`}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={cols.length}
                  className="px-4 py-6 text-center text-muted-foreground"
                >
                  Sem dados no período.
                </td>
              </tr>
            )}
            {rows.map((r, i) => (
              <tr key={i} className="border-b last:border-0">
                {r.map((cell, j) => (
                  <td
                    key={j}
                    className={`px-4 py-2 ${
                      j > 0 ? "text-right tabular-nums" : "font-medium"
                    }`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function SerieDiaria({
  serie,
}: {
  serie: { dia: string; criados: number; finalizados: number }[];
}) {
  const max = Math.max(1, ...serie.map((s) => s.criados));
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Volume por dia</CardTitle>
      </CardHeader>
      <CardContent>
        {serie.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Sem dados no período.
          </p>
        ) : (
          <div className="space-y-1">
            {serie.slice(-14).map((s) => (
              <div key={s.dia} className="flex items-center gap-2 text-xs">
                <span className="w-16 text-muted-foreground">
                  {s.dia.slice(5)}
                </span>
                <div className="h-3 flex-1 rounded bg-muted">
                  <div
                    className="h-3 rounded bg-primary/60"
                    style={{ width: `${(s.criados / max) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right tabular-nums">{s.criados}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
