"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Image as ImageIcon,
  MessageSquare,
  Mic,
  Rocket,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  IaAlerta,
  OpenRouterModelo,
  RankingModelo,
  SaudeFuncao,
  SaudeModelo,
} from "@/lib/api";

/**
 * Aba "Visão geral" do Saúde de IA (F3): as 4 funções do Nexus com o modelo
 * REALMENTE em uso, cruzando OpenRouter (uptime/latência) com a nossa
 * operação (ia_execucao 24h) — + comparativo de benchmarks dos curados.
 */

const ALERTA_LABEL: Record<string, string> = {
  uptime: "Uptime baixo",
  latencia: "Latência alta",
  throughput: "Throughput baixo",
  erros_proprios: "Erros na nossa operação",
  modelo_sumiu: "Modelo sem endpoints",
};

function quandoCurto(iso: string): string {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (min < 60) return `há ${Math.max(min, 1)} min`;
  const h = Math.round(min / 60);
  return h < 48 ? `há ${h} h` : `há ${Math.round(h / 24)} dias`;
}

const FUNCOES_META = {
  texto: { label: "Texto (agentes)", icon: MessageSquare },
  imagem: { label: "Imagem (visão)", icon: ImageIcon },
  audio: { label: "Áudio (transcrição + voz)", icon: Mic },
  documentos: { label: "Documentos (OCR)", icon: FileText },
} as const;

function uptimeBadge(v: number | null) {
  if (v == null) return <span className="text-muted-foreground">sem dado</span>;
  const variant = v >= 99 ? "success" : v >= 97 ? "warning" : "destructive";
  return <Badge variant={variant}>{v.toFixed(1)}%</Badge>;
}

function ms(v: number | null): string {
  return v == null ? "—" : `${Math.round(v)}ms`;
}

/** 2,0e12 tokens → "2,0 tri" — a escala do mercado, não a nossa. */
function tokensFmt(n: number): string {
  if (n >= 1e12)
    return `${(n / 1e12).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} tri`;
  if (n >= 1e9)
    return `${(n / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} bi`;
  if (n >= 1e6)
    return `${(n / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
  return n.toLocaleString("pt-BR");
}

export function VisaoGeral({
  funcoes,
  saude,
  modelos,
  rankings,
  alertas,
}: {
  funcoes: SaudeFuncao[];
  saude: Record<string, SaudeModelo>;
  modelos: OpenRouterModelo[];
  rankings: { ultimo_dia: string | null; items: RankingModelo[] } | null;
  alertas: { ativos: IaAlerta[]; resolvidos: IaAlerta[] } | null;
}) {
  // useState lazy: Date.now() é impuro pro lint do React Compiler — congela
  // o corte no primeiro render, que é o que queremos mesmo.
  const [corte30d] = useState(() => Date.now() - 30 * 24 * 3600_000);
  const lancamentos = modelos
    .filter((m) => m.criado_no_or && new Date(m.criado_no_or).getTime() > corte30d)
    .sort(
      (a, b) =>
        new Date(b.criado_no_or!).getTime() - new Date(a.criado_no_or!).getTime()
    )
    .slice(0, 5);

  const curados = modelos
    .filter((m) => m.promovido)
    .map((m) => ({
      slug: m.slug,
      intel: m.benchmarks?.artificial_analysis?.intelligence_index ?? null,
      cod: m.benchmarks?.artificial_analysis?.coding_index ?? null,
      inMtok: Number(m.pricing?.prompt) * 1_000_000 || null,
      outMtok: Number(m.pricing?.completion) * 1_000_000 || null,
    }))
    .sort((a, b) => (b.intel ?? -1) - (a.intel ?? -1));

  return (
    <div className="space-y-4">
      {alertas && alertas.ativos.length > 0 ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="size-4" />
              Degradação detectada ({alertas.ativos.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {alertas.ativos.map((a) => (
              <p key={a.id} className="text-sm">
                <span className="font-medium">
                  {ALERTA_LABEL[a.tipo] ?? a.tipo}
                </span>{" "}
                — <span className="font-mono text-xs">{a.modelo_slug}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · desde {quandoCurto(a.criado_em)}
                </span>
              </p>
            ))}
            <p className="pt-1 text-xs text-muted-foreground">
              O alerta resolve sozinho quando a condição normaliza. Aviso
              enviado no WhatsApp da VSA{" "}
              {"\u2014"} limiares: uptime &lt;97%, latência &gt;2× o normal,
              throughput &lt;50%, erros próprios &gt;20%.
            </p>
          </CardContent>
        </Card>
      ) : alertas ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CheckCircle2 className="size-3.5 text-success" />
          Nenhuma degradação detectada nos modelos em uso
          {alertas.resolvidos.length > 0
            ? ` \u00b7 \u00faltimo alerta resolvido ${quandoCurto(
                alertas.resolvidos[0].resolvido_em ?? alertas.resolvidos[0].criado_em
              )}`
            : ""}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {funcoes.map((f) => {
          const meta = FUNCOES_META[f.funcao];
          const Icone = meta.icon;
          return (
            <Card key={f.funcao}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Icone className="size-4" /> {meta.label}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {f.modelos.map((slug) => {
                  const s = saude[slug];
                  return (
                    <div key={slug} className="space-y-1 text-sm">
                      <p className="truncate font-mono text-xs">{slug}</p>
                      <div className="flex flex-wrap items-center gap-2">
                        {uptimeBadge(s?.uptime_30m ?? null)}
                        <span
                          className="text-muted-foreground"
                          title="Latência p50 do OpenRouter / a nossa medida (24h)"
                        >
                          OR {ms(s?.latencia_p50_ms ?? null)} · nós{" "}
                          {ms(s?.nossa_p50_ms ?? null)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        24h: {s?.chamadas_24h ?? 0} chamadas
                        {s && s.erros_24h > 0 ? (
                          <span className="text-destructive">
                            {" "}
                            · {s.erros_24h} erros
                          </span>
                        ) : (
                          " · 0 erros"
                        )}{" "}
                        · US${(s?.custo_24h_usd ?? 0).toFixed(4)}
                      </p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {rankings && rankings.items.length > 0 ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Rankings do mercado — tokens/dia no OpenRouter (
              {rankings.ultimo_dia})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {rankings.items.map((r, i) => {
              const max = rankings.items[0]?.total_tokens || 1;
              return (
                <div
                  key={r.slug}
                  className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 text-sm sm:grid-cols-[1.5rem_minmax(8rem,20rem)_1fr_auto]"
                >
                  <span className="text-xs text-muted-foreground">
                    {i + 1}.
                  </span>
                  <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <Link
                      href={`/catalog/openrouter/modelo/${r.slug}`}
                      className="break-all font-mono text-xs underline-offset-2 hover:underline"
                    >
                      {r.slug}
                    </Link>
                    {r.promovido ? (
                      <Badge variant="success" className="shrink-0">
                        curado
                      </Badge>
                    ) : null}
                  </span>
                  <div className="order-last col-span-full h-2 rounded-full bg-muted sm:order-none sm:col-span-1">
                    <div
                      className="h-full rounded-full bg-chart-2"
                      style={{
                        width: `${Math.max(2, (r.total_tokens / max) * 100)}%`,
                      }}
                    />
                  </div>
                  <span className="whitespace-nowrap text-right text-xs text-muted-foreground">
                    {tokensFmt(r.total_tokens)} · {r.share_pct.toFixed(1)}%
                    {r.delta_7d_pct != null ? (
                      <span
                        className={
                          r.delta_7d_pct >= 0
                            ? "text-success"
                            : "text-destructive"
                        }
                      >
                        {" "}
                        {r.delta_7d_pct >= 0 ? "▲" : "▼"}
                        {Math.abs(r.delta_7d_pct).toFixed(0)}% 7d
                      </span>
                    ) : null}
                  </span>
                </div>
              );
            })}
            <p className="pt-1 text-xs text-muted-foreground">
              Uso agregado da plataforma OpenRouter inteira (dataset oficial,
              janela de 30 dias) — versões datadas do mesmo modelo somadas.
              Não é o nosso consumo.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {rankings && rankings.items.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <TrendingUp className="size-4 text-success" /> Em alta (7d)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {[...rankings.items]
                .filter((r) => (r.delta_7d_pct ?? 0) > 0)
                .sort((a, b) => (b.delta_7d_pct ?? 0) - (a.delta_7d_pct ?? 0))
                .slice(0, 5)
                .map((r) => (
                  <p key={r.slug} className="flex items-baseline justify-between gap-2 text-sm">
                    <Link
                      href={`/catalog/openrouter/modelo/${r.slug}`}
                      className="min-w-0 break-all font-mono text-xs underline-offset-2 hover:underline"
                    >
                      {r.slug}
                    </Link>
                    <span className="shrink-0 text-xs text-success">
                      ▲{Math.abs(r.delta_7d_pct ?? 0).toFixed(0)}%
                    </span>
                  </p>
                ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <TrendingDown className="size-4 text-destructive" /> Em queda (7d)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {[...rankings.items]
                .filter((r) => (r.delta_7d_pct ?? 0) < 0)
                .sort((a, b) => (a.delta_7d_pct ?? 0) - (b.delta_7d_pct ?? 0))
                .slice(0, 5)
                .map((r) => (
                  <p key={r.slug} className="flex items-baseline justify-between gap-2 text-sm">
                    <Link
                      href={`/catalog/openrouter/modelo/${r.slug}`}
                      className="min-w-0 break-all font-mono text-xs underline-offset-2 hover:underline"
                    >
                      {r.slug}
                    </Link>
                    <span className="shrink-0 text-xs text-destructive">
                      ▼{Math.abs(r.delta_7d_pct ?? 0).toFixed(0)}%
                    </span>
                  </p>
                ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Rocket className="size-4 text-chart-1" /> Lançamentos (30d)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {lancamentos.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Nenhum modelo lançado nos últimos 30 dias.
                </p>
              ) : (
                lancamentos.map((m) => (
                  <p key={m.slug} className="flex items-baseline justify-between gap-2 text-sm">
                    <Link
                      href={`/catalog/openrouter/modelo/${m.slug}`}
                      className="min-w-0 break-all font-mono text-xs underline-offset-2 hover:underline"
                    >
                      {m.slug}
                    </Link>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {new Date(m.criado_no_or!).toLocaleDateString("pt-BR")}
                    </span>
                  </p>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            Benchmarks dos modelos curados
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Modelo</TableHead>
                  <TableHead>Inteligência</TableHead>
                  <TableHead>Código</TableHead>
                  <TableHead>Entrada /Mtok</TableHead>
                  <TableHead>Saída /Mtok</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {curados.map((m) => (
                  <TableRow key={m.slug}>
                    <TableCell>
                      <span className="font-mono text-xs">{m.slug}</span>
                    </TableCell>
                    <TableCell>
                      {m.intel != null ? (
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-chart-1"
                              style={{
                                width: `${Math.min(100, (m.intel / 70) * 100)}%`,
                              }}
                            />
                          </div>
                          {Math.round(m.intel)}
                        </div>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{m.cod != null ? Math.round(m.cod) : "—"}</TableCell>
                    <TableCell>
                      {m.inMtok != null ? `$${m.inMtok.toFixed(2)}` : "—"}
                    </TableCell>
                    <TableCell>
                      {m.outMtok != null ? `$${m.outMtok.toFixed(2)}` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
