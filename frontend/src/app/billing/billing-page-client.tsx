"use client";

import { useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  History,
  Loader2,
  Lock,
  Minus,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { usePermissionsContext } from "@/components/permissions-context";
import { usePlano } from "@/components/plano-context";
import { ApiError } from "@/components/ui/api-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BillingTransacao, PlanoCatalogo, TierContexto } from "@/lib/api";
import { dataCivil, dataHora } from "@/lib/formato";
import {
  ROTULO_FEATURE,
  featureLiberada,
  formatarLimite,
  fraseUpgrade,
  rotuloFeature,
} from "@/lib/plano";
import { cn } from "@/lib/utils";

import {
  loadBillingHistoricoAction,
  loadPlanosCatalogoAction,
  setPlanoLinksAction,
} from "./actions";

/**
 * Plano e cobrança (ADR-005 leva D).
 *
 * A tabela compara os planos pelas CHAVES REAIS de `plano.features` e pelas
 * colunas de limite — as mesmas que a API usa para devolver 402 e que o
 * worker usa para degradar. Antes era uma lista de marketing que não batia
 * com o que o código aplica (`docs/PLANOS_RECURSOS.md`).
 *
 * `?feature=<chave>` é o destino dos cadeados do menu e das telas: a página
 * abre explicando o recurso e destaca a linha dele.
 *
 * Assinar (leva F, D7/D12): cada plano pago tem o link do plano hospedado
 * na InfinitePay ("Recomendado" — Pix sem taxa ou cartão) e no Mercado Pago
 * (cartão recorrente). O cliente paga lá; a ativação é manual pelo
 * superadmin (Empresas → Plano e vigência), que confirma por WhatsApp. Só o
 * Free fica sem link. O botão "Assinar" do Asaas saiu porque nunca
 * funcionou em produção.
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
  const { isSuperadmin } = usePermissionsContext();
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
            {plano.valido_ate && (
              <p
                className={cn(
                  "text-sm",
                  plano.dias_para_vencer !== null && plano.dias_para_vencer < 0
                    ? "text-destructive"
                    : "text-muted-foreground"
                )}
              >
                {plano.dias_para_vencer !== null && plano.dias_para_vencer < 0
                  ? `Venceu em ${dataCivil(plano.valido_ate)}`
                  : `Válido até ${dataCivil(plano.valido_ate)}`}
              </p>
            )}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {plano.upgrade_sugerido
              ? `A coluna do plano ${
                  planos.find((p) => p.slug === plano.upgrade_sugerido)?.nome ?? plano.upgrade_sugerido
                } mostra o que é liberado ao subir de plano.`
              : "Este é o plano mais completo."}
          </p>
        </div>
      )}

      {planos.some((p) => p.link_infinitepay || p.link_mercadopago) && (
        <SecaoAssinar planos={planos} atual={plano?.slug ?? null} />
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
          <History className="size-4" /> Histórico de pagamentos
        </h2>
        {historico.isPending ? (
          <p className="py-3 text-sm text-muted-foreground">Carregando…</p>
        ) : historico.isError ? (
          <ApiError error={historico.error} onRetry={() => historico.refetch()} />
        ) : (
          <HistoricoTable items={historico.data} />
        )}
      </section>

      {isSuperadmin && catalogo.data && <EditorLinks planos={catalogo.data} />}
    </div>
  );
}

/**
 * Cards de assinatura: só os planos com link. Quem já está no plano vê
 * "Renovar"; os demais, "Assinar". InfinitePay em destaque (D12); Mercado
 * Pago como alternativa. Só o Free não tem venda self-service.
 */
function SecaoAssinar({ planos, atual }: { planos: PlanoCatalogo[]; atual: string | null }) {
  const vendaveis = planos.filter((p) => p.link_infinitepay || p.link_mercadopago);
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
        Assinar ou renovar
      </h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {vendaveis.map((p) => {
          const ehAtual = p.slug === atual;
          const verbo = ehAtual ? "Renovar" : "Assinar";
          return (
            <div
              key={p.slug}
              className={cn(
                "space-y-3 rounded-xl border p-4",
                ehAtual ? "border-brand-primary/50 bg-brand-primary/5" : "border-border bg-card"
              )}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-lg font-semibold">{p.nome}</p>
                <p className="text-sm text-muted-foreground">
                  {p.preco_mensal_brl ? `R$ ${p.preco_mensal_brl.toFixed(0)}/mês` : ""}
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {p.link_infinitepay && (
                  <Button
                    nativeButton={false}
                    render={
                      <a href={p.link_infinitepay} target="_blank" rel="noopener noreferrer" />
                    }
                    className="w-full justify-between"
                  >
                    <span>
                      {verbo} pela InfinitePay
                      <span className="ml-2 rounded bg-primary-foreground/20 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide">
                        Recomendado
                      </span>
                    </span>
                    <ExternalLink className="size-4" />
                  </Button>
                )}
                {p.link_mercadopago && (
                  <Button
                    variant="outline"
                    nativeButton={false}
                    render={
                      <a href={p.link_mercadopago} target="_blank" rel="noopener noreferrer" />
                    }
                    className="w-full justify-between"
                  >
                    <span>{verbo} pelo Mercado Pago</span>
                    <ExternalLink className="size-4" />
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                InfinitePay: Pix sem taxa (lembrete a cada mês) ou cartão com cobrança automática.
                Mercado Pago: cartão com cobrança automática.
              </p>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Depois do pagamento, a nossa equipe confirma e a vigência aparece aqui — você recebe a
        confirmação pelo WhatsApp cadastrado no resumo diário.
      </p>
    </section>
  );
}

/** Só superadmin: cola os links criados nos painéis dos gateways (mig 194). */
function EditorLinks({ planos }: { planos: PlanoCatalogo[] }) {
  const queryClient = useQueryClient();
  const editaveis = planos.filter((p) => p.slug !== "free");
  return (
    <section className="rounded-xl border border-dashed border-border p-4">
      <h2 className="text-sm font-medium">Links dos planos hospedados (superadmin)</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Crie o plano no painel da InfinitePay (Cobrança Recorrente) e do Mercado Pago (Assinaturas)
        e cole o link aqui. Vazio = plano sem venda pelo painel. Só links https dos próprios
        gateways são aceitos.
      </p>
      <div className="mt-3 space-y-3">
        {editaveis.map((p) => (
          <LinhaLinks
            key={p.slug}
            plano={p}
            onSalvo={() => void queryClient.invalidateQueries({ queryKey: ["planos-catalogo"] })}
          />
        ))}
      </div>
    </section>
  );
}

function LinhaLinks({ plano, onSalvo }: { plano: PlanoCatalogo; onSalvo: () => void }) {
  const [ip, setIp] = useState(plano.link_infinitepay ?? "");
  const [mp, setMp] = useState(plano.link_mercadopago ?? "");
  const [saving, startSaving] = useTransition();
  function salvar() {
    startSaving(async () => {
      const r = await setPlanoLinksAction(plano.slug, {
        link_infinitepay: ip.trim() || null,
        link_mercadopago: mp.trim() || null,
      });
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      toast.success(`Links do plano ${plano.nome} salvos.`);
      onSalvo();
    });
  }
  return (
    <div className="grid grid-cols-1 items-end gap-2 md:grid-cols-[8rem_1fr_1fr_auto]">
      <p className="text-sm font-medium">{plano.nome}</p>
      <div className="space-y-1">
        <Label htmlFor={`ip-${plano.slug}`} className="text-xs">
          InfinitePay
        </Label>
        <Input
          id={`ip-${plano.slug}`}
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="https://invoice.infinitepay.io/plans/…"
          disabled={saving}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`mp-${plano.slug}`} className="text-xs">
          Mercado Pago
        </Label>
        <Input
          id={`mp-${plano.slug}`}
          value={mp}
          onChange={(e) => setMp(e.target.value)}
          placeholder="https://mpago.la/…"
          disabled={saving}
        />
      </div>
      <Button type="button" variant="outline" size="sm" onClick={salvar} disabled={saving}>
        {saving ? <Loader2 className="size-4 animate-spin" /> : null}
        Salvar
      </Button>
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
            <th className="text-left">Plano</th>
            <th className="text-left">Período</th>
            <th className="text-left">Descrição</th>
            <th className="text-right">Valor</th>
            <th className="text-center">Situação</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-b border-border/60">
              <td className="py-2 text-xs text-muted-foreground">{dataHora(t.created_at)}</td>
              <td className="text-xs">{t.plano_nome || "—"}</td>
              <td className="text-xs">
                {t.periodo_inicio
                  ? `${dataCivil(t.periodo_inicio)} a ${dataCivil(t.periodo_fim)}`
                  : "—"}
              </td>
              <td className="text-xs">{t.descricao || "—"}</td>
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
