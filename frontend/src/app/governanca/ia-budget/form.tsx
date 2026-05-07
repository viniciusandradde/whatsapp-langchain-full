"use client";

import { useState, useTransition } from "react";
import { Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";

import { saveBudgetAction } from "./actions";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

export function BudgetForm({
  initial,
}: {
  initial: {
    limite_usd: number;
    acao_estouro: "alertar" | "bloquear" | "redirecionar_menu";
    alerta_pct: number;
  };
}) {
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        setSuccess(false);
        const fd = new FormData(e.currentTarget);
        startTransition(async () => {
          const r = await saveBudgetAction(fd);
          if (r.ok) {
            setSuccess(true);
          } else {
            setError(r.error ?? "Erro ao salvar.");
          }
        });
      }}
      className="space-y-4"
    >
      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}
      {success && (
        <p className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300">
          Budget atualizado.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label className={labelCls}>Limite mensal (USD) *</label>
          <input
            name="limite_usd"
            type="number"
            min={0}
            step={0.01}
            required
            defaultValue={initial.limite_usd}
            className={inputCls}
          />
        </div>
        <div className="space-y-1">
          <label className={labelCls}>Alertar em (%)</label>
          <input
            name="alerta_pct"
            type="number"
            min={1}
            max={100}
            defaultValue={initial.alerta_pct}
            className={inputCls}
          />
          <p className={helpCls}>Notifica admin quando consumo &gt;= esse %</p>
        </div>
        <div className="space-y-1">
          <label className={labelCls}>Ação ao estourar</label>
          <select
            name="acao_estouro"
            defaultValue={initial.acao_estouro}
            className={inputCls}
          >
            <option value="alertar">Apenas alertar (continua)</option>
            <option value="bloquear">Bloquear chamadas IA</option>
            <option value="redirecionar_menu">Redirecionar pro menu</option>
          </select>
        </div>
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>
          {pending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Salvar budget
        </Button>
      </div>
    </form>
  );
}
