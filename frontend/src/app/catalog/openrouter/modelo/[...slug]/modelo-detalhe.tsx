"use client";

import { AnaliseModelo, type AnaliseModeloData } from "@/components/analise-modelo";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HistoricoModelo } from "@/lib/api";

import { EventosFeed } from "../../eventos-feed";
import { Sparkline } from "../../sparkline";

function tokensFmt(n: number): string {
  if (n >= 1e12)
    return `${(n / 1e12).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} tri`;
  if (n >= 1e9)
    return `${(n / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} bi`;
  return `${(n / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
}

export function ModeloDetalhe({
  analise,
  historico,
}: {
  analise: AnaliseModeloData;
  historico: HistoricoModelo;
}) {
  const uptimes = historico.metricas.map((m) => m.uptime);
  const latencias = historico.metricas.map((m) => m.latencia_p50);
  const posicoes = historico.ranking.map((r) => r.pos);
  const tokens = historico.ranking.map((r) => r.tokens);

  return (
    <div className="space-y-4">
      <AnaliseModelo data={analise} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Uptime — 7 dias</CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline
              valores={uptimes}
              cor="var(--chart-1)"
              formato={(v) => `${v.toFixed(1)}%`}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Melhor endpoint por hora, da nossa coleta a cada 10 min.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Latência p50 — 7 dias</CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline
              valores={latencias}
              cor="var(--chart-1)"
              formato={(v) => `${Math.round(v)}ms`}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Menor p50 entre os endpoints — o caminho que o roteador
              escolheria.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Posição no ranking do mercado
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline
              valores={posicoes}
              cor="var(--chart-1)"
              invertido
              formato={(v) => `#${Math.round(v)}`}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Entre os ~50 modelos do dataset diário do OpenRouter — pra cima
              é melhor.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Tokens/dia no mercado</CardTitle>
          </CardHeader>
          <CardContent>
            <Sparkline
              valores={tokens}
              cor="var(--chart-1)"
              formato={tokensFmt}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Uso da plataforma OpenRouter inteira — não é o nosso consumo.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Novidades deste modelo</CardTitle>
        </CardHeader>
        <CardContent>
          <EventosFeed eventos={historico.eventos} comLink={false} />
        </CardContent>
      </Card>
    </div>
  );
}
