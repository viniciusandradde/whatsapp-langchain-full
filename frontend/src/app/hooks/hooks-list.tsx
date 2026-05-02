"use client";

import { useState, useTransition } from "react";
import { History, Pencil, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Hook, HookEvento, HookLog } from "@/lib/api";

import {
  deleteHookAction,
  loadHookLogsAction,
  saveHook,
} from "./actions";

interface Props {
  hooks: Hook[];
  eventos: HookEvento[];
}

type Editing = Hook | "new" | null;

export function HooksList({ hooks, eventos }: Props) {
  const [editing, setEditing] = useState<Editing>(null);
  const [logsFor, setLogsFor] = useState<number | null>(null);
  const [logs, setLogs] = useState<HookLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleDelete(id: number) {
    if (!confirm("Excluir este hook? Os logs também serão removidos.")) return;
    setError(null);
    startTransition(async () => {
      const r = await deleteHookAction(id);
      if (!r.ok) setError(r.error);
    });
  }

  async function openLogs(id: number) {
    setLogsFor(id);
    setLogsLoading(true);
    const r = await loadHookLogsAction(id);
    if (r.ok) setLogs(r.logs);
    else setError(r.error);
    setLogsLoading(false);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Hooks fazem POST HTTP em URL externa quando eventos internos
          acontecem. Use o <strong>secret</strong> para validar o
          <code className="ml-1 rounded bg-muted px-1 font-mono text-xs">
            X-Webhook-Signature
          </code>{" "}
          (HMAC-SHA256 do body) no destino.
        </p>
        {editing !== "new" && (
          <Button onClick={() => setEditing("new")} variant="default">
            <Plus className="size-4" />
            Novo hook
          </Button>
        )}
      </div>

      {editing === "new" && (
        <HookForm eventos={eventos} onDone={() => setEditing(null)} />
      )}
      {editing && editing !== "new" && (
        <HookForm
          eventos={eventos}
          initial={editing}
          onDone={() => setEditing(null)}
        />
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {hooks.length === 0 && !editing && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhum hook cadastrado</p>
          <p className="mt-1 text-sm">
            Configure URLs externas pra ser notificado de eventos do CRM.
          </p>
        </div>
      )}

      {hooks.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {hooks.map((h) => (
            <Card key={h.id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">{h.nome}</CardTitle>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {h.evento}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Badge variant={h.ativo ? "default" : "outline"}>
                      {h.ativo ? "ativo" : "inativo"}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {h.url}
                </p>
                {h.secret && (
                  <p className="text-xs text-muted-foreground">
                    🔐 secret configurado
                  </p>
                )}
              </CardContent>
              <div className="flex items-center justify-end gap-2 px-4 pb-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openLogs(h.id)}
                  disabled={isPending}
                >
                  <History className="size-3.5" />
                  Logs
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditing(h)}
                  disabled={isPending}
                >
                  <Pencil className="size-3.5" />
                  Editar
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(h.id)}
                  disabled={isPending}
                >
                  <Trash2 className="size-3.5" />
                  Excluir
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {logsFor !== null && (
        <LogsPanel
          hookId={logsFor}
          logs={logs}
          loading={logsLoading}
          onClose={() => setLogsFor(null)}
        />
      )}
    </div>
  );
}

function HookForm({
  eventos,
  initial,
  onDone,
}: {
  eventos: HookEvento[];
  initial?: Hook;
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveHook(initial?.id ?? null, form);
      if (!r.ok) setError(r.error);
      else onDone();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{initial ? "Editar hook" : "Novo hook"}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="nome"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Nome
              </label>
              <input
                id="nome"
                name="nome"
                defaultValue={initial?.nome ?? ""}
                required
                maxLength={120}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>

            <div>
              <label
                htmlFor="evento"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Evento
              </label>
              <select
                id="evento"
                name="evento"
                defaultValue={initial?.evento ?? eventos[0] ?? ""}
                required
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {eventos.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="url"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              URL
            </label>
            <input
              id="url"
              name="url"
              type="url"
              defaultValue={initial?.url ?? ""}
              required
              maxLength={2048}
              placeholder="https://exemplo.com/webhooks/nexus"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label
              htmlFor="secret"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              Secret <span className="normal-case">(opcional)</span>
            </label>
            <input
              id="secret"
              name="secret"
              defaultValue={initial?.secret ?? ""}
              maxLength={256}
              placeholder="usado pra X-Webhook-Signature"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="ativo"
              defaultChecked={initial?.ativo ?? true}
              className="size-4"
            />
            Ativo
          </label>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function LogsPanel({
  hookId,
  logs,
  loading,
  onClose,
}: {
  hookId: number;
  logs: HookLog[];
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-xl flex-col bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">Últimas tentativas — hook #{hookId}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
          {!loading && logs.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nenhuma tentativa registrada ainda.
            </p>
          )}
          <ul className="space-y-2">
            {logs.map((log) => {
              const ok = log.error == null && (log.status_code ?? 0) < 400;
              return (
                <li
                  key={log.id}
                  className="rounded-md border bg-background/40 p-3 text-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge
                      variant={ok ? "default" : "destructive"}
                      className="font-mono"
                    >
                      {log.status_code ?? "ERR"}
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">
                      {new Date(log.created_at).toLocaleString("pt-BR")}
                    </span>
                  </div>
                  <p className="mt-1.5 truncate text-xs text-muted-foreground">
                    {log.evento} · {log.duration_ms ?? "—"}ms
                  </p>
                  {log.error && (
                    <p className="mt-1 break-words text-xs text-destructive">
                      {log.error}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </aside>
    </div>
  );
}
