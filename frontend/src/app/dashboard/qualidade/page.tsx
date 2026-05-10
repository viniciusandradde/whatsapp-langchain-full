import {
  Award,
  MessageSquareText,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getNPSPorDepartamento,
  getNPSRankingOperadores,
  getNPSResumo,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ComentariosList } from "./comentarios-list";

export const dynamic = "force-dynamic";

const fmtN = (n: number) => n.toLocaleString("pt-BR");
const fmtScore = (s: number | null) =>
  s === null ? "—" : (s > 0 ? "+" : "") + s.toFixed(1);
const fmtPct = (n: number | null) => (n === null ? "—" : `${n.toFixed(1)}%`);
const fmtNota = (n: number | null) => (n === null ? "—" : n.toFixed(2));

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 50) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 0) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function scoreLabel(score: number | null): string {
  if (score === null) return "—";
  if (score >= 70) return "Excelente";
  if (score >= 50) return "Muito bom";
  if (score >= 0) return "Razoável";
  return "Crítico";
}

interface PageProps {
  searchParams: Promise<{ periodo?: string }>;
}

export default async function DashboardQualidadePage({
  searchParams,
}: PageProps) {
  await requireSession();
  const params = await searchParams;
  const periodo = Number(params.periodo ?? 30);

  let resumo, depto, ranking;
  let error: string | null = null;
  try {
    [resumo, depto, ranking] = await Promise.all([
      getNPSResumo(periodo),
      getNPSPorDepartamento(periodo),
      getNPSRankingOperadores(periodo),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar relatórios.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Award className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">NPS / Qualidade</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Avaliações dos atendimentos nos últimos {periodo} dias
          </p>
        </div>
        <div className="flex gap-1 text-xs">
          {[7, 30, 90].map((d) => (
            <a
              key={d}
              href={`/dashboard/qualidade?periodo=${d}`}
              className={`rounded px-2 py-1 ${
                periodo === d
                  ? "bg-primary text-primary-foreground"
                  : "border bg-background hover:bg-muted"
              }`}
            >
              {d}d
            </a>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {resumo && (
        <>
          {/* Cards superiores */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-sm font-normal text-muted-foreground">
                  NPS Score
                  <TrendingUp className="h-4 w-4" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  className={`text-4xl font-bold ${scoreColor(resumo.score)}`}
                >
                  {fmtScore(resumo.score)}
                </div>
                <Badge variant="secondary" className="mt-2 text-xs">
                  {scoreLabel(resumo.score)}
                </Badge>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-sm font-normal text-muted-foreground">
                  Avaliações
                  <MessageSquareText className="h-4 w-4" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{fmtN(resumo.total)}</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  CSAT médio: {fmtNota(resumo.csat_medio)} / 10
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-sm font-normal text-muted-foreground">
                  Promotores
                  <ThumbsUp className="h-4 w-4 text-emerald-500" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">
                  {fmtPct(resumo.pct_promotores)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {fmtN(resumo.promotores)} (notas 9-10)
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-sm font-normal text-muted-foreground">
                  Detratores
                  <ThumbsDown className="h-4 w-4 text-red-500" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-red-600 dark:text-red-400">
                  {fmtPct(resumo.pct_detratores)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {fmtN(resumo.detratores)} (notas 0-6)
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Por departamento */}
          {depto && depto.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Por departamento</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2">Departamento</th>
                      <th className="px-4 py-2 text-right">Avaliações</th>
                      <th className="px-4 py-2 text-right">NPS</th>
                      <th className="px-4 py-2 text-right">CSAT</th>
                      <th className="px-4 py-2 text-right">Promot.</th>
                      <th className="px-4 py-2 text-right">Detrat.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {depto.map((d, i) => (
                      <tr key={`${d.departamento_id ?? "null"}-${i}`} className="border-b last:border-0">
                        <td className="px-4 py-2">
                          {d.departamento_nome ?? (
                            <span className="text-muted-foreground italic">
                              sem departamento
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right">{fmtN(d.total)}</td>
                        <td className={`px-4 py-2 text-right font-semibold ${scoreColor(d.score)}`}>
                          {fmtScore(d.score)}
                        </td>
                        <td className="px-4 py-2 text-right">{fmtNota(d.csat_medio)}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">
                          {fmtN(d.promotores)}
                        </td>
                        <td className="px-4 py-2 text-right text-red-600 dark:text-red-400">
                          {fmtN(d.detratores)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {/* Ranking operadores */}
          {ranking && ranking.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Ranking de operadores</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2">#</th>
                      <th className="px-4 py-2">Atendente</th>
                      <th className="px-4 py-2 text-right">Avaliações</th>
                      <th className="px-4 py-2 text-right">NPS</th>
                      <th className="px-4 py-2 text-right">CSAT</th>
                      <th className="px-4 py-2 text-right">Promot.</th>
                      <th className="px-4 py-2 text-right">Detrat.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranking.map((r, i) => (
                      <tr key={r.user_id ?? i} className="border-b last:border-0">
                        <td className="px-4 py-2 font-mono text-xs text-muted-foreground">
                          {i + 1}
                        </td>
                        <td className="px-4 py-2">
                          {r.nome ?? (
                            <span className="text-muted-foreground italic">
                              sem nome
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right">{fmtN(r.avaliacoes_total)}</td>
                        <td className={`px-4 py-2 text-right font-semibold ${scoreColor(r.score)}`}>
                          {fmtScore(r.score)}
                        </td>
                        <td className="px-4 py-2 text-right">{fmtNota(r.csat_medio)}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">
                          {fmtN(r.promotores)}
                        </td>
                        <td className="px-4 py-2 text-right text-red-600 dark:text-red-400">
                          {fmtN(r.detratores)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}

          {/* Comentários (client component pra paginação + filter) */}
          <ComentariosList periodo={periodo} />
        </>
      )}
    </div>
  );
}
