"use client";

import { useEffect, useState } from "react";
import { ArrowUpCircle, BarChart3, CheckCircle2, Crown } from "lucide-react";

import type { QuotaSnapshot } from "@/lib/api";

import { fetchCurrentEmpresaIdAction, fetchQuotaAction } from "./actions";

interface Props {
  /** Se omitido, descobre via cookie active_empresa_id (Server Action). */
  empresaId?: number;
}

const PLAN_COLORS: Record<string, string> = {
  free: "bg-slate-500/15 text-slate-300 border-slate-500/40",
  pro: "bg-blue-500/15 text-blue-300 border-blue-500/40",
  enterprise: "bg-amber-500/15 text-amber-300 border-amber-500/40",
};

const RECURSO_LABEL: Record<string, string> = {
  conexoes: "Conexões WhatsApp",
  usuarios: "Usuários",
  atendimentos_mes: "Atendimentos (mês)",
  documentos_kb: "Documentos KB",
};

export function QuotaCard({ empresaId }: Props) {
  const [quota, setQuota] = useState<QuotaSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    (async () => {
      const eid = empresaId ?? (await fetchCurrentEmpresaIdAction());
      if (eid === null) {
        if (active) {
          setError("Empresa não definida");
          setLoading(false);
        }
        return;
      }
      const r = await fetchQuotaAction(eid);
      if (!active) return;
      if (r.ok) setQuota(r.quota);
      else setError(r.error);
      setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [empresaId]);

  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-obsidian-900 p-4">
        <div className="h-4 w-32 animate-pulse rounded bg-white/10" />
        <div className="mt-3 h-16 animate-pulse rounded bg-white/5" />
      </div>
    );
  }

  if (error || !quota) {
    return (
      <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Quota: {error || "indisponível"}
      </div>
    );
  }

  const planColor =
    PLAN_COLORS[quota.plano.slug] || PLAN_COLORS.free;
  const algumAlto = Object.values(quota.percentual).some(
    (p) => p !== null && p >= 85
  );
  const algumEstourou = Object.values(quota.percentual).some(
    (p) => p !== null && p >= 100
  );

  return (
    <div className="rounded-xl border border-white/10 bg-obsidian-900 p-4 space-y-4">
      {/* Header: plano atual + upgrade */}
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            <BarChart3 className="h-3 w-3" />
            Uso do plano
          </p>
          <p className="flex items-center gap-2 text-sm">
            <span
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${planColor}`}
            >
              {quota.plano.slug === "enterprise" && <Crown className="h-3 w-3" />}
              {quota.plano.nome}
            </span>
            {quota.plano.preco_mensal_brl > 0 && (
              <span className="text-xs text-muted-foreground">
                R${" "}
                {quota.plano.preco_mensal_brl.toLocaleString("pt-BR", {
                  minimumFractionDigits: 2,
                })}
                /mês
              </span>
            )}
          </p>
        </div>
        {quota.upgrade_sugerido && (algumAlto || algumEstourou) && (
          <UpgradeButton upgradeTo={quota.upgrade_sugerido} estourou={algumEstourou} />
        )}
      </div>

      {/* Barras por recurso */}
      <div className="space-y-2.5">
        {(["conexoes", "usuarios", "atendimentos_mes", "documentos_kb"] as const).map(
          (recurso) => (
            <QuotaRow
              key={recurso}
              label={RECURSO_LABEL[recurso]}
              usado={quota.usado[recurso]}
              limite={quota.limites[recurso]}
              percentual={quota.percentual[recurso]}
            />
          )
        )}
      </div>

      {/* Features habilitadas (badges) */}
      {Object.keys(quota.features).length > 0 && (
        <div className="space-y-1.5 border-t border-white/5 pt-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Features
          </p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(quota.features).map(([feat, enabled]) => (
              <span
                key={feat}
                className={
                  "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs " +
                  (enabled
                    ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                    : "bg-slate-500/10 text-slate-500 border border-slate-500/20")
                }
              >
                {enabled && <CheckCircle2 className="h-3 w-3" />}
                {feat}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QuotaRow({
  label,
  usado,
  limite,
  percentual,
}: {
  label: string;
  usado: number;
  limite: number | null;
  percentual: number | null;
}) {
  // Limite null = ilimitado (enterprise)
  if (limite === null) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-mono">
            {usado.toLocaleString("pt-BR")} <span className="text-muted-foreground">/ ∞</span>
          </span>
        </div>
        <div className="h-1.5 rounded-full bg-emerald-500/15">
          <div className="h-1.5 w-full rounded-full bg-emerald-500/40" />
        </div>
      </div>
    );
  }

  const p = percentual ?? 0;
  const color =
    p >= 100
      ? "bg-red-500"
      : p >= 85
        ? "bg-amber-500"
        : p >= 70
          ? "bg-yellow-500"
          : "bg-emerald-500";
  const widthPct = Math.min(p, 100);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={"font-mono " + (p >= 100 ? "text-red-400 font-medium" : "")}>
          {usado.toLocaleString("pt-BR")}
          <span className="text-muted-foreground">
            {" "}/ {limite.toLocaleString("pt-BR")}
          </span>
          <span className="ml-1 text-muted-foreground">({p.toFixed(0)}%)</span>
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className={"h-full transition-all " + color}
          style={{ width: `${widthPct}%` }}
        />
      </div>
    </div>
  );
}

function UpgradeButton({
  upgradeTo,
  estourou,
}: {
  upgradeTo: string;
  estourou: boolean;
}) {
  return (
    <a
      href="/companies"
      className={
        "inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors " +
        (estourou
          ? "border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20"
          : "border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20")
      }
    >
      <ArrowUpCircle className="h-3 w-3" />
      Upgrade pra {upgradeTo.charAt(0).toUpperCase() + upgradeTo.slice(1)}
    </a>
  );
}
