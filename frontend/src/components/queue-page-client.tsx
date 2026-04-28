"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ListOrdered,
  Clock,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
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
  attempts: number;
  error: string | null;
}

interface QueueData {
  counters: QueueCounters;
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
                  <TableHead>Tentativas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.messages.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
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
