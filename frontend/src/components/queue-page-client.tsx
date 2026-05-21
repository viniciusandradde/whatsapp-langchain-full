"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ListOrdered,
  Clock,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Hourglass,
  Gauge,
  Activity,
  TrendingUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface QueueCounters {
  queued: number;
  processing: number;
  done: number;
  failed: number;
}

interface QueueMessage {
  id: number;
  phone_number: string;
  agent_id: string;
  incoming_message: string;
  status: string;
  created_at: string | null;
  processed_at: string | null;
  attempts: number;
  error: string | null;
  age_seconds: number | null;
  latency_seconds: number | null;
}

interface QueueMetrics {
  oldest_queued_age_seconds: number;
  throughput_last_hour_per_min: number;
  throughput_last_hour_total: number;
  failure_rate_pct_24h: number;
  avg_latency_seconds_24h: number | null;
  p95_latency_seconds_24h: number | null;
}

interface QueueData {
  counters: QueueCounters;
  metrics: QueueMetrics;
  messages: QueueMessage[];
}

const POLL_INTERVAL_MS = 5000;

const STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  queued: { label: "Na fila", variant: "outline" },
  processing: { label: "Processando", variant: "default" },
  done: { label: "Concluido", variant: "secondary" },
  failed: { label: "Falhou", variant: "destructive" },
};

function formatPhone(phone: string): string {
  if (phone.length > 4) {
    return `***${phone.slice(-4)}`;
  }

  return phone;
}

function truncateText(text: string, maxLength: number = 40): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function formatDate(isoDate: string | null): string {
  if (!isoDate) return "—";

  try {
    return new Date(isoDate).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoDate;
  }
}

function secondsAgo(timestamp: number): number {
  return Math.floor((Date.now() - timestamp) / 1000);
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m}m${s}s` : `${m}m`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h${m}m` : `${h}h`;
}

function ageColorClass(seconds: number | null, status: string): string {
  // Só destaca quando está esperando (queued/processing). Done/failed = neutro.
  if (status !== "queued" && status !== "processing") {
    return "text-muted-foreground";
  }
  if (seconds === null) return "text-muted-foreground";
  if (seconds > 300) return "text-red-600 font-medium";
  if (seconds > 60) return "text-amber-600 font-medium";
  return "text-muted-foreground";
}

function metricCardColor(
  kind: "oldest" | "throughput" | "failure" | "latency",
  value: number | null
): string {
  if (value === null) return "text-muted-foreground";
  if (kind === "oldest") {
    if (value > 300) return "text-red-600";
    if (value > 60) return "text-amber-600";
    return "text-emerald-600";
  }
  if (kind === "failure") {
    if (value > 5) return "text-red-600";
    if (value > 2) return "text-amber-600";
    return "text-emerald-600";
  }
  if (kind === "latency") {
    if (value > 15) return "text-red-600";
    if (value > 8) return "text-amber-600";
    return "text-emerald-600";
  }
  // throughput — neutro (mais é melhor mas depende do tier do projeto)
  return "text-blue-600";
}

export function QueuePageClient() {
  const [data, setData] = useState<QueueData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);

  const fetchQueue = useCallback(async () => {
    try {
      const response = await fetch("/api/queue");

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || `Erro ${response.status}`);
      }

      const result: QueueData = await response.json();
      setData(result);
      setError(null);
      setLastUpdated(Date.now());
    } catch (fetchError) {
      const message =
        fetchError instanceof Error
          ? fetchError.message
          : "Erro desconhecido ao buscar fila";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();

    const interval = setInterval(fetchQueue, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  useEffect(() => {
    const tick = setInterval(() => {
      setElapsed(secondsAgo(lastUpdated));
    }, 1000);

    return () => clearInterval(tick);
  }, [lastUpdated]);

  if (loading && !data) {
    return <QueueSkeleton />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListOrdered className="h-6 w-6" />
          <h1 className="text-2xl font-semibold">Fila</h1>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          <span>Atualizado ha {elapsed}s</span>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Erro ao atualizar a fila</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {data && (
        <>
          {/* Contadores (hoje) */}
          <div>
            <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Contadores de hoje
            </h2>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm text-muted-foreground">
                    Na fila
                  </CardTitle>
                  <Clock className="h-4 w-4 text-yellow-500" />
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-yellow-600">
                  {data.counters.queued}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm text-muted-foreground">
                    Processando
                  </CardTitle>
                  <Loader2 className="h-4 w-4 text-blue-500" />
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-blue-600">
                  {data.counters.processing}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm text-muted-foreground">
                    Concluidos
                  </CardTitle>
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold text-green-600">
                  {data.counters.done}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm text-muted-foreground">
                    Falhas
                  </CardTitle>
                  <AlertTriangle
                    className={
                      data.counters.failed > 0
                        ? "h-4 w-4 text-red-500"
                        : "h-4 w-4 text-muted-foreground"
                    }
                  />
                </div>
              </CardHeader>
              <CardContent>
                <p
                  className={
                    data.counters.failed > 0
                      ? "text-3xl font-bold text-red-600"
                      : "text-3xl font-bold text-muted-foreground"
                  }
                >
                  {data.counters.failed}
                </p>
              </CardContent>
            </Card>
            </div>
          </div>

          {/* Métricas operacionais — visão de saúde da fila */}
          <div>
            <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Saúde da fila
            </h2>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle
                      className="text-sm text-muted-foreground"
                      title="Idade da mensagem mais antiga ainda em 'queued'. Esperado <30s; >5min indica saturação."
                    >
                      Msg mais antiga (queued)
                    </CardTitle>
                    <Hourglass
                      className={
                        "h-4 w-4 " +
                        metricCardColor(
                          "oldest",
                          data.metrics.oldest_queued_age_seconds
                        )
                      }
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  <p
                    className={
                      "text-3xl font-bold " +
                      metricCardColor(
                        "oldest",
                        data.metrics.oldest_queued_age_seconds
                      )
                    }
                  >
                    {data.counters.queued === 0
                      ? "—"
                      : formatDuration(data.metrics.oldest_queued_age_seconds)}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle
                      className="text-sm text-muted-foreground"
                      title="Taxa de processamento — msgs concluídas por minuto nos últimos 60 minutos. Capacidade ~12 msg/min por worker; com 4 workers ~48 msg/min."
                    >
                      Throughput (1h)
                    </CardTitle>
                    <TrendingUp className="h-4 w-4 text-blue-500" />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold text-blue-600">
                    {data.metrics.throughput_last_hour_per_min.toFixed(1)}
                    <span className="ml-1 text-sm font-normal text-muted-foreground">
                      /min
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {data.metrics.throughput_last_hour_total} msgs na última hora
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle
                      className="text-sm text-muted-foreground"
                      title="Percentual de mensagens que falharam nas últimas 24h (após esgotar retries). Alerta se >2%; investigar se >5%."
                    >
                      Taxa de falha (24h)
                    </CardTitle>
                    <Gauge
                      className={
                        "h-4 w-4 " +
                        metricCardColor("failure", data.metrics.failure_rate_pct_24h)
                      }
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  <p
                    className={
                      "text-3xl font-bold " +
                      metricCardColor("failure", data.metrics.failure_rate_pct_24h)
                    }
                  >
                    {data.metrics.failure_rate_pct_24h.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle
                      className="text-sm text-muted-foreground"
                      title="Latência: tempo entre msg entrar na fila e ser concluída. P95 mostra a cauda lenta (95% das msgs ficam abaixo desse valor)."
                    >
                      Latência (24h)
                    </CardTitle>
                    <Activity
                      className={
                        "h-4 w-4 " +
                        metricCardColor(
                          "latency",
                          data.metrics.p95_latency_seconds_24h
                        )
                      }
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  <p
                    className={
                      "text-3xl font-bold " +
                      metricCardColor(
                        "latency",
                        data.metrics.p95_latency_seconds_24h
                      )
                    }
                  >
                    {formatDuration(data.metrics.p95_latency_seconds_24h)}
                    <span className="ml-1 text-sm font-normal text-muted-foreground">
                      p95
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    avg {formatDuration(data.metrics.avg_latency_seconds_24h)}
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Telefone</TableHead>
                  <TableHead>Agente</TableHead>
                  <TableHead className="hidden md:table-cell">
                    Mensagem
                  </TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden sm:table-cell">
                    Criado em
                  </TableHead>
                  <TableHead
                    className="text-right"
                    title="Tempo desde que entrou na fila"
                  >
                    Idade
                  </TableHead>
                  <TableHead
                    className="hidden text-right md:table-cell"
                    title="Tempo entre created_at e processed_at (apenas msgs concluídas/falhas)"
                  >
                    Latência
                  </TableHead>
                  <TableHead className="text-center">Tentativas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.messages.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={9}
                      className="py-8 text-center text-muted-foreground"
                    >
                      Nenhuma mensagem na fila
                    </TableCell>
                  </TableRow>
                ) : (
                  data.messages.map((message) => {
                    const statusInfo = STATUS_CONFIG[message.status] || {
                      label: message.status,
                      variant: "outline" as const,
                    };

                    return (
                      <TableRow key={message.id}>
                        <TableCell className="font-mono text-xs">
                          {message.id}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {formatPhone(message.phone_number)}
                        </TableCell>
                        <TableCell className="text-xs">
                          {message.agent_id}
                        </TableCell>
                        <TableCell
                          className="hidden max-w-[200px] truncate text-xs md:table-cell"
                          title={message.incoming_message}
                        >
                          {truncateText(message.incoming_message)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={statusInfo.variant}>
                            {statusInfo.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="hidden text-xs text-muted-foreground sm:table-cell">
                          {formatDate(message.created_at)}
                        </TableCell>
                        <TableCell
                          className={
                            "text-right text-xs " +
                            ageColorClass(message.age_seconds, message.status)
                          }
                        >
                          {formatDuration(message.age_seconds)}
                        </TableCell>
                        <TableCell className="hidden text-right text-xs text-muted-foreground md:table-cell">
                          {formatDuration(message.latency_seconds)}
                        </TableCell>
                        <TableCell className="text-center">
                          {message.attempts}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}

function QueueSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ListOrdered className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Fila</h1>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index}>
            <CardHeader>
              <Skeleton className="h-4 w-20" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-9 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="space-y-3 rounded-xl border p-4">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    </div>
  );
}
