/**
 * Sprint J — Dashboard pessoal do atendente.
 * Mostra KPIs do mês: resolvidos hoje, abertos, resolvidos 30d, tempo médio.
 */

import Link from "next/link";
import { ArrowLeft, BarChart3 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getMyDashboard, type AtendenteDashboard } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const min = seconds / 60;
  if (min < 60) return `${Math.round(min)}min`;
  const h = min / 60;
  return `${h.toFixed(1)}h`;
}

export default async function MyDashboardPage() {
  await requireSession();

  let data: AtendenteDashboard | null = null;
  let error: string | null = null;
  try {
    data = await getMyDashboard();
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar dashboard.";
  }

  return (
    <div className="space-y-6">
      <Link
        href="/atendentes"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar para Atendentes
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <BarChart3 className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Meu Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Sua produção de hoje e dos últimos 30 dias.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {data && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Kpi
            label="Resolvidos hoje"
            value={data.resolvidos_hoje}
            hint="Atendimentos fechados (resolvido/abandonado) com data de hoje"
          />
          <Kpi
            label="Em atendimento"
            value={data.abertos}
            hint="Atendimentos abertos atribuídos a você"
          />
          <Kpi
            label="Resolvidos (30d)"
            value={data.resolvidos_30d}
            hint="Total resolvido nos últimos 30 dias"
          />
          <Kpi
            label="Tempo médio (30d)"
            value={formatDuration(data.avg_segundos_resolucao_30d)}
            hint="Tempo entre abertura e fechamento (resolvido)"
          />
        </div>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold">{value}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}
