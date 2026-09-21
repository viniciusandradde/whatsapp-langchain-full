"use client";

import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  CreditCard,
  History,
  Loader2,
  Lock,
  Minus,
  X,
} from "lucide-react";

import { usePlano } from "@/components/plano-context";
import { ApiError } from "@/components/ui/api-error";
import { Badge } from "@/components/ui/badge";
import type { BillingTransacao, PlanoCatalogo, TierContexto } from "@/lib/api";
import { dataHora } from "@/lib/formato";
import {
  ROTULO_FEATURE,
  featureLiberada,
  formatarLimite,
  fraseUpgrade,
  rotuloFeature,
} from "@/lib/plano";
import { cn } from "@/lib/utils";

import { loadBillingHistoricoAction, loadPlanosCatalogoAction } from "./actions";

/**
 * Plano e cobrança (ADR-005 leva D).
 *
 * A tabela compara os planos pelas CHAVES REAIS de `plano.features` e pelas
 * colunas de limite — as mesmas que a API usa para devolver 402 e que o
 * worker usa para degradar. Antes era uma lista de marketing que não batia
 * com o que o código aplica (`docs/PLANOS_RECURSOS.md`).
 *
 * `?feature=<chave>` é o destino dos cadeados do menu e das telas: a página
 * abre explicando o recurso e destaca a linha dele. A troca de plano em si
 * chega na leva F (planos hospedados nos gateways, ativação pelo superadmin);
 * o botão "Assinar" do Asaas saiu porque nunca funcionou em produção (D7).
 */

const TIER_ROTULO: Record<TierContexto, string> = {
  lite: "Lite (6 mil caracteres)",
  regular: "Regular (15 mil)",
  medium: "Medium (25 mil)",
  large: "Large (35 mil)",
  extended: "Extended (300 mil)",
};

interface LinhaLimite {
  /** Chave da coluna do plano OU de `features` (tetos numéricos, mig 192). */
  chave: string;
  rotulo: string;
  valor: (p: PlanoCatalogo) => string;
}

function dias(v: unknown): string {
  if (v === null || v === undefined) return "Sem limite";
  return typeof v === "number" ? `${v} dias` : "—";
}

function teto(v: unknown): string {
  if (v === null || v === undefined) return "Ilimitado";
  return typeof v === "number" ? v.toLocaleString("pt-BR") : "—";
}

const LIMITES: LinhaLimite[] = [
  { chave: "limite_conexoes", rotulo: "Conexões de WhatsApp", valor: (p) => formatarLimite(p.limite_conexoes) },
  { chave: "limite_usuarios", rotulo: "Usuários", valor: (p) => formatarLimite(p.limite_usuarios) },
  { chave: "limite_agentes", rotulo: "Agentes de IA", valor: (p) => formatarLimite(p.limite_agentes) },
  { chave: "limite_atendimentos_mes", rotulo: "Atendimentos por mês", valor: (p) => formatarLimite(p.limite_atendimentos_mes) },
  { chave: "limite_documentos_kb", rotulo: "Documentos na base de conhecimento", valor: (p) => formatarLimite(p.limite_documentos_kb) },
  { chave: "departamentos_max", rotulo: "Departamentos", valor: (p) => teto(p.features.departamentos_max) },
  { chave: "workflows_max", rotulo: "Workflows ativos", valor: (p) => teto(p.features.workflows_max) },
  { chave: "menus_max", rotulo: "Menus de chatbot", valor: (p) => teto(p.features.menus_max) },
  {
    chave: "orcamento_ia",
    rotulo: "Orçamento de IA por mês",
    valor: (p) =>
      p.limite_orcamento_ia_usd == null ? "Sem teto" : `até US$ ${p.limite_orcamento_ia_usd.toFixed(0)}`,
  },
  {
    chave: "contexto_max",
    rotulo: ROTULO_FEATURE.contexto_max,
    valor: (p) => {
      const t = p.features.contexto_max;
      return typeof t === "string" && t in TIER_ROTULO ? TIER_ROTULO[t as TierContexto] : "—";
    },
  },
  { chave: "retencao_max_dias", rotulo: ROTULO_FEATURE.retencao_max_dias, valor: (p) => dias(p.features.retencao_max_dias) },
  { chave: "auditoria_dias", rotulo: ROTULO_FEATURE.auditoria_dias, valor: (p) => dias(p.features.auditoria_dias) },
];

/** Recursos booleanos, agrupados por onde o cliente os encontra no painel. */
const RECURSOS: { grupo: string; chaves: string[] }[] = [
  { grupo: "Atendimento", chaves: ["csat", "resumo_diario", "transcricao_operador", "calendar"] },
  {
    grupo: "Agente de IA",
    chaves: [
      "fewshot",
      "imagem_cliente",
      "documentos_cliente",
      "voz",
      "modelos_premium",
      "catalogo_completo",
      "bateria_testes",
      "qualidade_ia",
    ],
  },
  { grupo: "Canais e integrações", chaves: ["waba", "webhooks", "disparador", "disparador_media"] },
  { grupo: "Painel", chaves: ["menu_moderno", "rbac", "white_label", "observabilidade"] },
];

export function BillingPageClient() {
  const { plano } = usePlano();
  const params = useSearchParams();
  const destaque = params.get("feature");

  const catalogo = useQuery({
    queryKey: ["planos-catalogo"],
    queryFn: async () => {
      const r = await loadPlanosCatalogoAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 10 * 60_000,
  });
  const historico = useQuery({
    queryKey: ["billing-historico"],
    queryFn: async () => {
      const r = await loadBillingHistoricoAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 60_000,
  });

  const planos = catalogo.data ?? [];
  const bloqueado = !!destaque && !!plano && !featureLiberada(plano.features, destaque);
  // O plano em que a chave destacada passa a existir — para a frase do banner.
  const planoQueLibera = destaque
    ? planos.find((p) => p.slug !== plano?.slug && featureLiberada(p.features, destaque))
    : undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <CreditCard className="size-5 text-brand-primary" />
          Plano e cobrança
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          O que está incluído no seu plano e o que muda ao subir de plano.
        </p>
      </div>

      {destaque && (
        <div
          role="status"
          className={cn(
            "flex items-start gap-2.5 rounded-lg border p-3 text-sm",
            bloqueado ? "border-warning/40 bg-warning/10" : "border-border bg-muted/40"
          )}
        >
          <Lock className={cn("mt-0.5 size-4 shrink-0", bloqueado ? "text-warning" : "text-muted-foreground")} />
          <p>
            <span className="font-medium">{rotuloFeature(destaque)}</span>
            {bloqueado && plano ? (
              <>
                {" "}
                não está no plano {plano.nome}.{" "}
                {planoQueLibera
                  ? `Disponível a partir do plano ${planoQueLibera.nome}.`
                  : fraseUpgrade(plano.upgrade_sugerido)}
              </>
            ) : (
              <> está incluído no seu plano.</>
            )}
          </p>
        </div>
      )}

      {plano && (
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Plano atual</p>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="text-xl font-semibold">{plano.nome}</p>
            <p className="text-sm text-muted-foreground">
              {plano.preco_mensal_brl > 0
                ? `R$ ${plano.preco_mensal_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}/mês`
                : "Sem mensalidade"}
            </p>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {plano.upgrade_sugerido
              ? `Para mudar de plano, fale com quem administra a plataforma — a coluna do plano ${
                  planos.find((p) => p.slug === plano.upgrade_sugerido)?.nome ?? plano.upgrade_sugerido
                } mostra o que é liberado.`
              : "Este é o plano mais completo."}
          </p>
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Comparação de planos
        </h2>
        {catalogo.isPending ? (
          <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Carregando planos…
          </div>
        ) : catalogo.isError ? (
          <ApiError error={catalogo.error} onRetry={() => catalogo.refetch()} />
        ) : (
          <TabelaPlanos planos={planos} atual={plano?.slug ?? null} destaque={destaque} />
        )}
      </section>

      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
          <History className="size-4" /> Histórico de cobranças
        </h2>
        {historico.isPending ? (
          <p className="py-3 text-sm text-muted-foreground">Carregando…</p>
        ) : historico.isError ? (
          <ApiError error={historico.error} onRetry={() => historico.refetch()} />
        ) : (
          <HistoricoTable items={historico.data} />
        )}
      </section>
    </div>
  );
}

function TabelaPlanos({
  planos,
  atual,
  destaque,
}: {
  planos: PlanoCatalogo[];
  atual: string | null;
  destaque: string | null;
}) {
  const colunaAtual = (slug: string) => slug === atual;
  const linhaDestaque = (chave: string) => chave === destaque;

  const th = "px-2 py-2 text-center text-xs font-medium";
  const tdRotulo =
    "sticky left-0 z-10 min-w-[11rem] bg-background px-2 py-1.5 text-left text-xs text-foreground";
  const td = "min-w-[4.5rem] px-2 py-1.5 text-center text-xs";

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className={cn(tdRotulo, "text-xs font-medium text-muted-foreground")}>Recurso</th>
            {planos.map((p) => (
              <th
                key={p.slug}
                scope="col"
                className={cn(th, colunaAtual(p.slug) && "bg-brand-primary/10")}
              >
                <div className="flex flex-col items-center gap-1">
                  <span className="text-sm font-semibold">{p.nome}</span>
                  <span className="font-normal text-muted-foreground">
                    {p.preco_mensal_brl ? `R$ ${p.preco_mensal_brl.toFixed(0)}/mês` : "R$ 0"}
                  </span>
                  {colunaAtual(p.slug) && (
                    <Badge variant="outline" className="border-brand-primary/50 text-brand-primary">
                      Seu plano
                    </Badge>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <LinhaGrupo titulo="Limites" colunas={planos.length} />
          {LIMITES.map((l) => (
            <tr
              key={l.chave}
              className={cn(
                "border-b border-border/60",
                linhaDestaque(l.chave) && "bg-warning/10"
              )}
            >
              <th scope="row" className={cn(tdRotulo, "font-normal", linhaDestaque(l.chave) && "bg-warning/10 font-medium")}>
                {l.rotulo}
              </th>
              {planos.map((p) => (
                <td
                  key={p.slug}
                  className={cn(td, "tabular-nums", colunaAtual(p.slug) && "bg-brand-primary/10")}
                >
                  {l.valor(p)}
                </td>
              ))}
            </tr>
          ))}
          {RECURSOS.map((g) => (
            <FragmentoGrupo key={g.grupo} titulo={g.grupo} chaves={g.chaves} planos={planos} colunaAtual={colunaAtual} linhaDestaque={linhaDestaque} tdRotulo={tdRotulo} td={td} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LinhaGrupo({ titulo, colunas }: { titulo: string; colunas: number }) {
  return (
    <tr className="border-b border-border bg-muted/40">
      <th
        scope="rowgroup"
        colSpan={colunas + 1}
        className="sticky left-0 px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground"
      >
        {titulo}
      </th>
    </tr>
  );
}

function FragmentoGrupo({
  titulo,
  chaves,
  planos,
  colunaAtual,
  linhaDestaque,
  tdRotulo,
  td,
}: {
  titulo: string;
  chaves: string[];
  planos: PlanoCatalogo[];
  colunaAtual: (slug: string) => boolean;
  linhaDestaque: (chave: string) => boolean;
  tdRotulo: string;
  td: string;
}) {
  return (
    <>
      <LinhaGrupo titulo={titulo} colunas={planos.length} />
      {chaves.map((chave) => (
        <tr
          key={chave}
          className={cn("border-b border-border/60", linhaDestaque(chave) && "bg-warning/10")}
        >
          <th scope="row" className={cn(tdRotulo, "font-normal", linhaDestaque(chave) && "bg-warning/10 font-medium")}>
            {rotuloFeature(chave)}
          </th>
          {planos.map((p) => {
            const tem = featureLiberada(p.features, chave);
            return (
              <td key={p.slug} className={cn(td, colunaAtual(p.slug) && "bg-brand-primary/10")}>
                {tem ? (
                  <Check className="mx-auto size-4 text-success" aria-label="Incluído" />
                ) : (
                  <Minus className="mx-auto size-4 text-muted-foreground/50" aria-label="Não incluído" />
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

function HistoricoTable({ items }: { items: BillingTransacao[] }) {
  if (items.length === 0) {
    return (
      <p className="py-3 text-sm text-muted-foreground">Nenhum pagamento registrado ainda.</p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase text-muted-foreground">
            <th className="py-2 text-left">Data</th>
            <th className="text-left">Descrição</th>
            <th className="text-left">Plano</th>
            <th className="text-right">Valor</th>
            <th className="text-center">Situação</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-b border-border/60">
              <td className="py-2 text-xs text-muted-foreground">{dataHora(t.created_at)}</td>
              <td className="text-xs">{t.descricao || "—"}</td>
              <td className="text-xs">{t.plano_nome || "—"}</td>
              <td className="text-right font-mono text-xs tabular-nums">
                R$ {t.valor_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
              </td>
              <td className="text-center">
                <StatusBadge status={t.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: BillingTransacao["status"] }) {
  const cfg: Record<string, { label: string; cor: string; icon?: React.ReactNode }> = {
    pago: { label: "Pago", cor: "bg-success/15 text-success", icon: <CheckCircle2 className="size-3" /> },
    pendente: { label: "Pendente", cor: "bg-warning/15 text-warning" },
    falhou: { label: "Falhou", cor: "bg-destructive/15 text-destructive", icon: <X className="size-3" /> },
    estornado: { label: "Estornado", cor: "bg-muted text-muted-foreground" },
    cancelado: { label: "Cancelado", cor: "bg-muted text-muted-foreground" },
  };
  const c = cfg[status] ?? { label: status, cor: "bg-muted text-muted-foreground" };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium", c.cor)}>
      {c.icon}
      {c.label}
    </span>
  );
}
