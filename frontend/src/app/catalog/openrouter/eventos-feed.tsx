"use client";

import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUpRight,
  DollarSign,
  Maximize2,
  PackageMinus,
  PackagePlus,
  Sparkles,
} from "lucide-react";

import type { OpenRouterEvento } from "@/lib/api";

/**
 * Feed de novidades do ecossistema (mig 181) — serve a aba Novidades e a
 * página de análise do modelo. Cada evento nasce de um diff entre syncs;
 * o texto aqui só traduz o detalhe pra linguagem de gente.
 */

const META: Record<
  string,
  { label: string; icon: typeof Sparkles; cor: string }
> = {
  modelo_novo: { label: "Modelo novo", icon: Sparkles, cor: "text-success" },
  modelo_voltou: {
    label: "Voltou ao catálogo",
    icon: PackagePlus,
    cor: "text-success",
  },
  modelo_removido: {
    label: "Saiu do catálogo",
    icon: PackageMinus,
    cor: "text-destructive",
  },
  preco_mudou: { label: "Preço mudou", icon: DollarSign, cor: "text-warning" },
  contexto_mudou: {
    label: "Contexto mudou",
    icon: Maximize2,
    cor: "text-muted-foreground",
  },
  entrou_top: {
    label: "Entrou no top 20",
    icon: ArrowUpRight,
    cor: "text-success",
  },
  saiu_top: {
    label: "Saiu do top 20",
    icon: ArrowDownRight,
    cor: "text-destructive",
  },
};

function precoMtok(porToken: unknown): string {
  const v = Number(porToken);
  if (!porToken || !Number.isFinite(v)) return "—";
  return `$${(v * 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}`;
}

function quando(iso: string): string {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (min < 60) return `há ${Math.max(min, 1)} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `há ${h} h`;
  return new Date(iso).toLocaleDateString("pt-BR");
}

function descricao(e: OpenRouterEvento): string {
  const d = e.detalhe ?? {};
  if (e.tipo === "modelo_novo") {
    const partes: string[] = [];
    if (d.prompt) partes.push(`entrada ${precoMtok(d.prompt)}/Mtok`);
    if (d.context_length)
      partes.push(
        `contexto ${Math.round(Number(d.context_length) / 1000)}K`
      );
    return partes.join(" · ");
  }
  if (e.tipo === "preco_mudou") {
    const pct = d.pct != null ? Number(d.pct) : null;
    const dir = pct != null ? (pct > 0 ? "subiu" : "caiu") : "mudou";
    const faixa =
      d.prompt_antes !== d.prompt_depois
        ? `entrada ${precoMtok(d.prompt_antes)} → ${precoMtok(d.prompt_depois)}`
        : `saída ${precoMtok(d.completion_antes)} → ${precoMtok(d.completion_depois)}`;
    return pct != null
      ? `${dir} ${Math.abs(pct).toFixed(0)}% — ${faixa}/Mtok`
      : `${faixa}/Mtok`;
  }
  if (e.tipo === "contexto_mudou")
    return `${Math.round(Number(d.antes) / 1000)}K → ${Math.round(Number(d.depois) / 1000)}K tokens`;
  if (e.tipo === "entrou_top" || e.tipo === "saiu_top")
    return d.pos ? `posição ${d.pos} · dia ${d.dia}` : "";
  return "";
}

export function EventosFeed({
  eventos,
  comLink = true,
}: {
  eventos: OpenRouterEvento[];
  comLink?: boolean;
}) {
  if (eventos.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nenhuma novidade registrada ainda — o feed nasce dos diffs entre
        sincronizações: lançamentos, preços, remoções e movimentos do top 20
        aparecem aqui conforme acontecem.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {eventos.map((e) => {
        const meta = META[e.tipo] ?? {
          label: e.tipo,
          icon: Sparkles,
          cor: "text-muted-foreground",
        };
        const Icone = meta.icon;
        const desc = descricao(e);
        return (
          <div key={e.id} className="flex items-start gap-2.5 text-sm">
            <Icone className={`mt-0.5 size-4 shrink-0 ${meta.cor}`} />
            <div className="min-w-0">
              <p>
                <span className="font-medium">{meta.label}</span>
                {" — "}
                {comLink ? (
                  <Link
                    href={`/catalog/openrouter/modelo/${e.modelo_slug}`}
                    className="break-all font-mono text-xs underline-offset-2 hover:underline"
                  >
                    {e.modelo_slug}
                  </Link>
                ) : (
                  <span className="break-all font-mono text-xs">
                    {e.modelo_slug}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {" "}
                  · {quando(e.criado_em)}
                </span>
              </p>
              {desc ? (
                <p className="text-xs text-muted-foreground">{desc}</p>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
