"use client";

/**
 * Client component que dispara/monitora runs E2E em tempo real (Sprint L).
 *
 * Estados:
 * - Lista histórica de runs (table) com link "Abrir Allure"
 * - Form pra disparar novo run (filtro -k opcional)
 * - Run em andamento: progress + log scrollable via SSE
 *
 * Conecta SSE em /api/proxy/sse/test-runs/{id} (Next.js proxy injeta auth).
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Loader2, Play, RefreshCw, StopCircle, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  getTestRunClient as getTestRun,
  getTestRunsClient as getTestRuns,
  killTestRunClient as killTestRun,
  startTestRunClient as startTestRun,
  type TestRun,
  type TestRunStatus,
} from "@/lib/test-runner-client";

const STATUS_VARIANT: Record<
  TestRunStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  queued: { label: "Na fila", variant: "secondary" },
  running: { label: "Rodando", variant: "default" },
  passed: { label: "Passou", variant: "outline" },
  failed: { label: "Falhou", variant: "destructive" },
  error: { label: "Erro", variant: "destructive" },
};

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const min = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${min}m${s.toString().padStart(2, "0")}s`;
}

interface Props {
  initialRuns: TestRun[];
}

export function TestRunnerClient({ initialRuns }: Props) {
  const [runs, setRuns] = useState(initialRuns);
  const [filtro, setFiltro] = useState("");
  const [activeRun, setActiveRun] = useState<TestRun | null>(
    initialRuns.find((r) => r.status === "running" || r.status === "queued") ||
      null
  );
  const [log, setLog] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const evtSrcRef = useRef<EventSource | null>(null);

  const refreshList = async () => {
    try {
      const r = await getTestRuns();
      setRuns(r.items);
    } catch (e) {
      console.warn("refresh runs failed", e);
    }
  };

  // SSE: abre quando há run em andamento
  useEffect(() => {
    if (!activeRun) return;
    if (activeRun.status !== "running" && activeRun.status !== "queued") return;

    const url = `/api/proxy/sse/test-runs/${activeRun.id}`;
    const es = new EventSource(url);
    evtSrcRef.current = es;

    es.addEventListener("snapshot", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as TestRun;
        setActiveRun(data);
      } catch {}
    });
    es.addEventListener("log_chunk", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as { chunk: string };
        setLog((prev) => prev + data.chunk);
        // Auto-scroll bottom
        setTimeout(() => {
          if (logRef.current) {
            logRef.current.scrollTop = logRef.current.scrollHeight;
          }
        }, 50);
      } catch {}
    });
    es.addEventListener("progress", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as TestRun;
        setActiveRun(data);
      } catch {}
    });
    es.addEventListener("done", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data) as TestRun;
        setActiveRun(data);
        void refreshList();
      } catch {}
      es.close();
      evtSrcRef.current = null;
    });
    es.addEventListener("error", () => {
      // Fallback: fecha SSE e refresh manual
      es.close();
      evtSrcRef.current = null;
    });

    return () => {
      es.close();
      evtSrcRef.current = null;
    };
  }, [activeRun?.id, activeRun?.status]);

  const handleStart = async () => {
    setStarting(true);
    setError(null);
    setLog("");
    try {
      const run = await startTestRun(filtro.trim() || undefined);
      setActiveRun(run);
      void refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao iniciar.");
    } finally {
      setStarting(false);
    }
  };

  const handleKill = async () => {
    if (!activeRun) return;
    if (!confirm("Parar o run em andamento? Subprocess receberá SIGTERM."))
      return;
    try {
      await killTestRun(activeRun.id);
      // SSE detecta status mudando e fecha
      const refreshed = await getTestRun(activeRun.id);
      setActiveRun(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao parar.");
    }
  };

  const isRunning =
    activeRun?.status === "running" || activeRun?.status === "queued";

  return (
    <div className="space-y-6">
      {/* Form de novo run */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Disparar nova bateria</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-muted-foreground">
                Filtro pytest -k (opcional)
              </label>
              <input
                type="text"
                value={filtro}
                onChange={(e) => setFiltro(e.target.value)}
                placeholder='Ex: "atendimento and texto" ou deixe vazio pra rodar 32 cenários'
                disabled={isRunning || starting}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleStart} disabled={isRunning || starting}>
                {starting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Play className="size-4" />
                )}
                {isRunning ? "Em andamento…" : "Iniciar"}
              </Button>
              {isRunning && (
                <Button variant="destructive" onClick={handleKill}>
                  <StopCircle className="size-4" />
                  Parar
                </Button>
              )}
            </div>
          </div>
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </CardContent>
      </Card>

      {/* Run ativo: log + progresso */}
      {activeRun && isRunning && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Run #{activeRun.id} —{" "}
                <Badge variant={STATUS_VARIANT[activeRun.status].variant}>
                  {STATUS_VARIANT[activeRun.status].label}
                </Badge>
              </CardTitle>
              <span className="text-xs text-muted-foreground">
                {activeRun.filtro
                  ? `filtro: ${activeRun.filtro}`
                  : "todos os cenários"}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <pre
              ref={logRef}
              className="h-72 overflow-y-auto rounded-md border bg-muted/30 p-3 font-mono text-xs leading-relaxed"
            >
              {log || "Aguardando log…"}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Histórico */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Histórico (últimos 50)</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refreshList()}
            >
              <RefreshCw className="size-3.5" />
              Atualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum run ainda. Clique em "Iniciar" pra disparar a primeira bateria.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="py-2 pr-2 text-left font-normal">#</th>
                  <th className="py-2 pr-2 text-left font-normal">Status</th>
                  <th className="py-2 pr-2 text-left font-normal">
                    Pass/Total
                  </th>
                  <th className="py-2 pr-2 text-left font-normal">Duração</th>
                  <th className="py-2 pr-2 text-left font-normal">Quando</th>
                  <th className="py-2 pr-2 text-left font-normal">Por</th>
                  <th className="py-2 pr-2 text-right font-normal">Ações</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const meta = STATUS_VARIANT[r.status];
                  return (
                    <tr key={r.id} className="border-b last:border-0">
                      <td className="py-2 pr-2 font-mono text-xs">{r.id}</td>
                      <td className="py-2 pr-2">
                        <Badge variant={meta.variant} className="text-[10px]">
                          {meta.label}
                        </Badge>
                      </td>
                      <td className="py-2 pr-2 font-mono text-xs">
                        {r.passed ?? "—"}/{r.total ?? "—"}
                      </td>
                      <td className="py-2 pr-2 font-mono text-xs">
                        {formatDuration(r.duration_seconds)}
                      </td>
                      <td className="py-2 pr-2 text-xs">
                        {r.started_at
                          ? new Date(r.started_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="py-2 pr-2 text-xs">
                        {r.started_by_name ?? r.started_by_user_id ?? "—"}
                      </td>
                      <td className="py-2 pr-2 text-right">
                        {(r.status === "passed" || r.status === "failed") && (
                          <Link
                            href={`/relatorios/allure/runs/${r.id}`}
                            className={cn(
                              "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
                              "hover:bg-accent"
                            )}
                          >
                            <ExternalLink className="size-3" />
                            Allure
                          </Link>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
