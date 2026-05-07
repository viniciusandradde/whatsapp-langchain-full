import Link from "next/link";
import { DollarSign, ArrowLeft, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getIaBudget } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { BudgetForm } from "./form";

export const dynamic = "force-dynamic";

export default async function IaBudgetPage() {
  await requireSession();

  let budget;
  let error: string | null = null;
  try {
    budget = await getIaBudget();
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar budget.";
  }

  return (
    <div className="space-y-6">
      <Link
        href="/dashboard/ia"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar pro dashboard
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <DollarSign className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">
            Budget IA — {budget?.ano_mes}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Limite mensal de gastos com LLM. Worker bloqueia/alerta/redireciona
            ao estourar.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {budget?.exists && budget.limite_usd !== undefined && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Status atual</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="flex items-center gap-2 text-sm">
              {budget.pct_consumo && budget.pct_consumo >= 80 && (
                <AlertTriangle className="size-4 text-yellow-500" />
              )}
              <span className="font-mono">
                ${budget.consumo_usd?.toFixed(2)} / ${budget.limite_usd?.toFixed(2)}
              </span>
              <span className="text-muted-foreground">
                ({budget.pct_consumo}%)
              </span>
            </p>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full ${
                  budget.pct_consumo && budget.pct_consumo >= 100
                    ? "bg-destructive"
                    : budget.pct_consumo && budget.pct_consumo >= (budget.alerta_pct ?? 80)
                    ? "bg-yellow-500"
                    : "bg-emerald-500"
                }`}
                style={{
                  width: `${Math.min(budget.pct_consumo ?? 0, 100)}%`,
                }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Ação ao estourar: <code>{budget.acao_estouro}</code>
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configurar budget mensal</CardTitle>
        </CardHeader>
        <CardContent>
          <BudgetForm
            initial={{
              limite_usd: budget?.limite_usd ?? 100,
              acao_estouro: (budget?.acao_estouro as "alertar" | "bloquear" | "redirecionar_menu") ?? "alertar",
              alerta_pct: budget?.alerta_pct ?? 80,
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
