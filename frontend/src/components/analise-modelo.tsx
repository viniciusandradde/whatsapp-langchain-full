"use client";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * Ficha de análise de um modelo do OpenRouter — o mesmo painel serve a aba
 * Modelo & Estilo do construtor (superadmin) e a página de comparação do
 * módulo Saúde de IA. Dumb component: recebe o payload da rota
 * `GET /api/openrouter/modelos/{slug}/analise` e só renderiza.
 */

export interface AnaliseModeloData {
  modelo: string;
  coletado_agora: boolean;
  catalogo: {
    nome: string;
    descricao: string | null;
    context_length: number | null;
    input_modalities: string[];
    output_modalities: string[];
    pricing: Record<string, string | null>;
    benchmarks: {
      artificial_analysis?: {
        intelligence_index?: number;
        coding_index?: number;
        agentic_index?: number;
      };
    };
    supported_parameters: string[];
  } | null;
  endpoints: {
    provider_tag: string;
    provider_nome: string;
    quantization: string | null;
    uptime_30m: number | null;
    latencia: { p50?: number; p90?: number } | null;
    throughput: { p50?: number } | null;
    coletado_em: string;
  }[];
}

function precoMtok(porToken: string | null | undefined): string {
  const v = Number(porToken);
  if (!porToken || !Number.isFinite(v) || v === 0) return "—";
  return `$${(v * 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}`;
}

function contexto(n: number | null): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString("pt-BR")}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

/** Cor do uptime por limiar — os mesmos cortes do futuro alerta (F4). */
function uptimeBadge(v: number | null) {
  if (v == null) return <span className="text-muted-foreground">—</span>;
  const variant = v >= 99 ? "success" : v >= 97 ? "warning" : "destructive";
  return <Badge variant={variant}>{v.toFixed(1)}%</Badge>;
}

export function AnaliseModelo({ data }: { data: AnaliseModeloData }) {
  const c = data.catalogo;
  const aa = c?.benchmarks?.artificial_analysis;
  return (
    <div className="space-y-3 rounded-md border border-foreground/[0.06] bg-foreground/[0.02] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium">{data.modelo}</span>
        {c?.input_modalities.map((m) => (
          <Badge key={m} variant="outline">
            {m}
          </Badge>
        ))}
        {aa?.intelligence_index != null ? (
          <Badge variant="secondary">
            inteligência {Math.round(aa.intelligence_index)}
          </Badge>
        ) : null}
        {aa?.coding_index != null ? (
          <Badge variant="secondary">código {Math.round(aa.coding_index)}</Badge>
        ) : null}
      </div>

      {c ? (
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">Entrada /Mtok</p>
            <p>{precoMtok(c.pricing?.prompt)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Saída /Mtok</p>
            <p>{precoMtok(c.pricing?.completion)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Cache /Mtok</p>
            <p>{precoMtok(c.pricing?.input_cache_read)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Contexto</p>
            <p>{contexto(c.context_length)}</p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Modelo fora do catálogo sincronizado — rode o sync em Catálogo
          OpenRouter para os dados completos.
        </p>
      )}

      {data.endpoints.length > 0 ? (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provedor</TableHead>
                <TableHead>Uptime 30m</TableHead>
                <TableHead>Latência p50/p90</TableHead>
                <TableHead>Tok/s p50</TableHead>
                <TableHead>Quant.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.endpoints.map((e) => (
                <TableRow key={e.provider_tag}>
                  <TableCell>
                    <span className="font-mono text-xs">{e.provider_tag}</span>
                  </TableCell>
                  <TableCell>{uptimeBadge(e.uptime_30m)}</TableCell>
                  <TableCell>
                    {e.latencia?.p50 != null
                      ? `${Math.round(e.latencia.p50)}ms / ${
                          e.latencia.p90 != null
                            ? `${Math.round(e.latencia.p90)}ms`
                            : "—"
                        }`
                      : "—"}
                  </TableCell>
                  <TableCell>{e.throughput?.p50 ?? "—"}</TableCell>
                  <TableCell>{e.quantization ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Sem métricas de provedor para este modelo.
        </p>
      )}
      {data.coletado_agora ? (
        <p className="text-xs text-muted-foreground">
          Métricas coletadas agora, sob demanda — este modelo passa a ter
          histórico a partir daqui.
        </p>
      ) : null}
    </div>
  );
}
