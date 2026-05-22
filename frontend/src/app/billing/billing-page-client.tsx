"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import {
  AlertCircle,
  ArrowUpCircle,
  Check,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  History,
  Loader2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { BillingStatus, BillingTransacao } from "@/lib/api";

import {
  cancelSubscriptionAction,
  checkoutAction,
  loadBillingHistoricoAction,
  loadBillingStatusAction,
} from "./actions";

interface Plano {
  slug: "free" | "pro" | "enterprise";
  nome: string;
  preco: string;
  destaque?: boolean;
  features: string[];
  limites: string[];
}

const PLANOS: Plano[] = [
  {
    slug: "free",
    nome: "Free",
    preco: "R$ 0",
    features: ["Suporte por email"],
    limites: ["1 conexão WhatsApp", "2 usuários", "100 atendimentos/mês", "5 docs KB"],
  },
  {
    slug: "pro",
    nome: "Pro",
    preco: "R$ 299/mês",
    destaque: true,
    features: ["Google Calendar", "RBAC granular", "Menu chatbot moderno", "Suporte prioritário"],
    limites: ["3 conexões WhatsApp", "10 usuários", "5.000 atendimentos/mês", "100 docs KB"],
  },
  {
    slug: "enterprise",
    nome: "Enterprise",
    preco: "R$ 1.499/mês",
    features: ["Tudo do Pro +", "MCP custom", "White label", "SLA + suporte dedicado"],
    limites: ["Conexões ∞", "Usuários ∞", "Atendimentos ∞", "Docs KB ∞"],
  },
];

export function BillingPageClient() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [historico, setHistorico] = useState<BillingTransacao[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" | "err"; message: string } | null
  >(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    const [s, h] = await Promise.all([
      loadBillingStatusAction(),
      loadBillingHistoricoAction(),
    ]);
    if (s.ok) setStatus(s.data);
    if (h.ok) setHistorico(h.data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  function handleUpgrade(plano: "pro" | "enterprise") {
    setFeedback(null);
    startTransition(async () => {
      const r = await checkoutAction(plano);
      if (r.ok) {
        if (r.data.payment_url) {
          // Redireciona pra checkout Asaas
          window.location.href = r.data.payment_url;
        } else {
          setFeedback({
            kind: "ok",
            message: `Assinatura ${r.data.plano} criada. Aguardando confirmação.`,
          });
          await loadAll();
        }
      } else {
        setFeedback({ kind: "err", message: r.error });
      }
    });
  }

  function handleCancel() {
    if (!confirm("Cancelar assinatura? Plano volta pra Free imediatamente.")) {
      return;
    }
    setFeedback(null);
    startTransition(async () => {
      const r = await cancelSubscriptionAction();
      if (r.ok) {
        setFeedback({ kind: "ok", message: "Assinatura cancelada." });
        await loadAll();
      } else {
        setFeedback({ kind: "err", message: r.error });
      }
    });
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-8 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando billing…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <CreditCard className="h-5 w-5 text-brand-primary" />
          Plano & Cobrança
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Gerencie sua assinatura. Cobrança via Asaas (cartão, PIX ou boleto).
        </p>
      </div>

      {feedback && (
        <div
          className={
            "flex items-center gap-2 rounded-lg border p-3 text-sm " +
            (feedback.kind === "ok"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-destructive/40 bg-destructive/10 text-destructive")
          }
        >
          {feedback.kind === "ok" ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          {feedback.message}
        </div>
      )}

      {/* Status atual */}
      {status && <PlanoAtualCard status={status} onCancel={handleCancel} pending={pending} />}

      {/* Comparativo + upgrade */}
      <div>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Planos disponíveis
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {PLANOS.map((p) => (
            <PlanoCard
              key={p.slug}
              plano={p}
              atual={status?.plano_atual === p.slug}
              onUpgrade={
                p.slug !== "free" ? () => handleUpgrade(p.slug as "pro" | "enterprise") : undefined
              }
              pending={pending}
            />
          ))}
        </div>
      </div>

      {/* Histórico */}
      <HistoricoTable items={historico} />
    </div>
  );
}

function PlanoAtualCard({
  status,
  onCancel,
  pending,
}: {
  status: BillingStatus;
  onCancel: () => void;
  pending: boolean;
}) {
  const ativa = !!status.asaas_subscription_id;
  return (
    <div className="rounded-xl border border-white/10 bg-obsidian-900 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Plano atual
          </p>
          <p className="mt-1 flex items-center gap-2 text-xl font-semibold">
            {status.plano_atual.toUpperCase()}
            {ativa ? (
              <span className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
                Assinatura ativa
              </span>
            ) : (
              <span className="rounded-md border border-slate-500/30 bg-slate-500/10 px-2 py-0.5 text-xs text-slate-400">
                Sem cobrança
              </span>
            )}
          </p>
          {status.valor_mensal && status.valor_mensal > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              R$ {status.valor_mensal.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}/mês
              · {status.total_pagamentos} pagamento(s)
              {status.ultimo_pagamento_em && (
                <>
                  {" "}
                  · último em {new Date(status.ultimo_pagamento_em).toLocaleDateString("pt-BR")}
                </>
              )}
            </p>
          )}
        </div>
        {ativa && (
          <Button variant="outline" disabled={pending} onClick={onCancel}>
            {pending ? "Cancelando…" : "Cancelar assinatura"}
          </Button>
        )}
      </div>
      {status.pendentes > 0 && (
        <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          {status.pendentes} cobrança(s) pendente(s). Verifique seu email ou o
          histórico abaixo.
        </div>
      )}
    </div>
  );
}

function PlanoCard({
  plano,
  atual,
  onUpgrade,
  pending,
}: {
  plano: Plano;
  atual: boolean;
  onUpgrade?: () => void;
  pending: boolean;
}) {
  return (
    <div
      className={
        "rounded-xl border p-4 space-y-3 " +
        (plano.destaque
          ? "border-brand-primary/50 bg-brand-primary/5"
          : "border-white/10 bg-obsidian-900")
      }
    >
      <div className="flex items-center justify-between">
        <p className="text-lg font-semibold">{plano.nome}</p>
        {atual && (
          <span className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
            Atual
          </span>
        )}
        {plano.destaque && !atual && (
          <span className="rounded-md border border-brand-primary/40 bg-brand-primary/10 px-2 py-0.5 text-xs text-brand-primary">
            Mais popular
          </span>
        )}
      </div>

      <p className="text-2xl font-bold">{plano.preco}</p>

      <div className="space-y-1.5">
        {plano.limites.map((l) => (
          <p key={l} className="flex items-center gap-2 text-xs text-muted-foreground">
            <Check className="h-3 w-3 text-emerald-500" /> {l}
          </p>
        ))}
        <div className="my-2 h-px bg-white/5" />
        {plano.features.map((f) => (
          <p key={f} className="flex items-center gap-2 text-xs text-foreground">
            <CheckCircle2 className="h-3 w-3 text-emerald-500" /> {f}
          </p>
        ))}
      </div>

      {onUpgrade && !atual && (
        <Button
          onClick={onUpgrade}
          disabled={pending}
          className="w-full"
        >
          {pending ? (
            "Processando…"
          ) : (
            <>
              <ArrowUpCircle className="mr-1 h-4 w-4" />
              Assinar {plano.nome}
            </>
          )}
        </Button>
      )}
      {atual && (
        <p className="text-center text-xs text-muted-foreground italic">
          Você está neste plano
        </p>
      )}
    </div>
  );
}

function HistoricoTable({ items }: { items: BillingTransacao[] }) {
  return (
    <div className="rounded-xl border border-white/10 bg-obsidian-900 p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
        <History className="h-4 w-4" /> Histórico de cobranças
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground italic py-3">
          Nenhuma transação registrada ainda.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase text-muted-foreground">
                <th className="text-left py-2">Data</th>
                <th className="text-left">Descrição</th>
                <th className="text-left">Plano</th>
                <th className="text-right">Valor</th>
                <th className="text-center">Status</th>
                <th className="text-center">Fatura</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="border-b border-white/5">
                  <td className="py-2 text-xs text-muted-foreground">
                    {new Date(t.created_at).toLocaleString("pt-BR", {
                      day: "2-digit", month: "2-digit", year: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </td>
                  <td className="text-xs">{t.descricao || "—"}</td>
                  <td className="text-xs">{t.plano_nome || "—"}</td>
                  <td className="text-right font-mono text-xs">
                    R$ {t.valor_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="text-center">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="text-center">
                    {t.gateway_id ? (
                      <a
                        href={`https://www.asaas.com/i/${t.gateway_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-brand-primary hover:underline"
                      >
                        <ExternalLink className="inline h-3 w-3" />
                      </a>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { label: string; color: string; icon?: React.ReactNode }> = {
    pago: { label: "Pago", color: "text-emerald-300 bg-emerald-500/15", icon: <CheckCircle2 className="h-3 w-3" /> },
    pendente: { label: "Pendente", color: "text-amber-300 bg-amber-500/15" },
    falhou: { label: "Falhou", color: "text-destructive bg-destructive/15", icon: <X className="h-3 w-3" /> },
    estornado: { label: "Estornado", color: "text-slate-300 bg-slate-500/15" },
    cancelado: { label: "Cancelado", color: "text-slate-400 bg-slate-500/10" },
  };
  const c = cfg[status] || { label: status, color: "text-slate-300 bg-slate-500/10" };
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium " + c.color
      }
    >
      {c.icon}
      {c.label}
    </span>
  );
}
