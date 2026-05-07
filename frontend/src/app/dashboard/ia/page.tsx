import { Activity, AlertTriangle, Brain, Bot, DollarSign, Hash, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getDashboardIa } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const fmtUSD = (n: number) =>
  n < 0.01 ? `$${n.toFixed(6)}` : `$${n.toFixed(2)}`;
const fmtN = (n: number) => n.toLocaleString("pt-BR");

interface PageProps {
  searchParams: Promise<{ days?: string }>;
}

export default async function DashboardIaPage({ searchParams }: PageProps) {
  await requireSession();
  const params = await searchParams;
  const days = Number(params.days ?? 30);

  let data;
  let error: string | null = null;
  try {
    data = await getDashboardIa(days);
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar dashboard.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Activity className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Dashboard IA</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Consumo + custo + top modelos/agentes nos últimos {data?.periodo_dias ?? days} dias
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {data && (
        <>
          {/* Cards resumo */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Resumo
              icon={Hash}
              label={`Calls (${data.periodo_dias}d)`}
              value={fmtN(data.resumo.total_calls)}
            />
            <Resumo
              icon={DollarSign}
              label="Custo período"
              value={fmtUSD(data.resumo.custo_periodo_usd)}
            />
            <Resumo
              icon={DollarSign}
              label="Custo mês atual"
              value={fmtUSD(data.resumo.custo_mes_atual_usd)}
            />
            <Resumo
              icon={Zap}
              label="Tokens input"
              value={fmtN(data.resumo.total_tokens_input)}
            />
            <Resumo
              icon={Zap}
              label="Tokens output"
              value={fmtN(data.resumo.total_tokens_output)}
            />
          </div>

          {/* Budget atual */}
          {data.budget_atual && (
            <Card
              className={
                data.budget_atual.estourado
                  ? "border-destructive/50"
                  : data.budget_atual.pct_consumo >= data.budget_atual.alerta_pct
                  ? "border-yellow-500/50"
                  : ""
              }
            >
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  {data.budget_atual.estourado && (
                    <AlertTriangle className="size-4 text-destructive" />
                  )}
                  Budget mensal — {fmtUSD(data.budget_atual.consumo_usd)} /{" "}
                  {fmtUSD(data.budget_atual.limite_usd)} (
                  {data.budget_atual.pct_consumo}%)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full ${
                      data.budget_atual.estourado
                        ? "bg-destructive"
                        : data.budget_atual.pct_consumo >= data.budget_atual.alerta_pct
                        ? "bg-yellow-500"
                        : "bg-emerald-500"
                    }`}
                    style={{
                      width: `${Math.min(data.budget_atual.pct_consumo, 100)}%`,
                    }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Ação ao estourar: <code>{data.budget_atual.acao_estouro}</code>
                  {" · "}
                  Alerta em <code>{data.budget_atual.alerta_pct}%</code>
                </p>
              </CardContent>
            </Card>
          )}

          {/* Série diária — render simples (barras CSS) */}
          {data.serie_diaria.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Custo diário ({data.serie_diaria.length} dias com atividade)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SerieDiaria items={data.serie_diaria} />
              </CardContent>
            </Card>
          )}

          {/* Top modelos */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Brain className="size-4" />
                  Top modelos
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.top_modelos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Sem chamadas no período.
                  </p>
                ) : (
                  <ul className="divide-y divide-border/50">
                    {data.top_modelos.map((m, i) => (
                      <li
                        key={`${m.provedor}/${m.nome}`}
                        className="flex items-center justify-between gap-3 py-2 text-sm"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium">
                            {i + 1}. {m.provedor}/{m.nome}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {fmtN(m.tokens_input)} in · {fmtN(m.tokens_output)} out
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-medium">{fmtUSD(m.custo)}</p>
                          <Badge variant="outline" className="text-[10px]">
                            {m.calls} calls
                          </Badge>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Bot className="size-4" />
                  Top agentes
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.top_agentes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Sem chamadas atribuídas a agentes DB no período.
                  </p>
                ) : (
                  <ul className="divide-y divide-border/50">
                    {data.top_agentes.map((a, i) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between gap-3 py-2 text-sm"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium">
                            {i + 1}. {a.nome}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            <code>{a.slug}</code>
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-medium">{fmtUSD(a.custo)}</p>
                          <Badge variant="outline" className="text-[10px]">
                            {a.calls} calls
                          </Badge>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Resumo({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Brain;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon className="size-3.5" />
          {label}
        </div>
        <p className="mt-1 text-xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

function SerieDiaria({
  items,
}: {
  items: { dia: string; calls: number; custo: number }[];
}) {
  const max = Math.max(...items.map((i) => i.custo), 0.0001);
  return (
    <div className="space-y-1">
      {items.map((it) => {
        const pct = (it.custo / max) * 100;
        return (
          <div key={it.dia} className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0 text-muted-foreground">
              {new Date(it.dia + "T00:00:00").toLocaleDateString("pt-BR", {
                day: "2-digit",
                month: "short",
              })}
            </span>
            <div className="relative h-5 flex-1 rounded bg-muted">
              <div
                className="absolute left-0 top-0 h-full rounded bg-primary/40"
                style={{ width: `${pct}%` }}
              />
              <span className="absolute right-1 top-0.5 text-[10px]">
                {fmtUSD(it.custo)} · {it.calls} calls
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
