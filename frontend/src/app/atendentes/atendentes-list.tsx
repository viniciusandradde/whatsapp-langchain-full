"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Search, Settings2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  AtendenteStatus,
  AtendenteStatusValor,
  Departamento,
} from "@/lib/api";

import { setMaxParalelosAction } from "./actions";

const STATUS_META: Record<
  AtendenteStatusValor | "indefinido",
  { label: string; cls: string }
> = {
  online: {
    label: "Online",
    cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
  },
  ausente: {
    label: "Ausente",
    cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40",
  },
  pausa: {
    label: "Em pausa",
    cls: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/40",
  },
  offline: {
    label: "Offline",
    cls: "bg-muted text-muted-foreground border-muted",
  },
  indefinido: {
    label: "Indefinido",
    cls: "bg-muted text-muted-foreground border-muted",
  },
};

const STATUS_DOT: Record<AtendenteStatusValor | "indefinido", string> = {
  online: "bg-emerald-500",
  ausente: "bg-amber-500",
  pausa: "bg-blue-500",
  offline: "bg-muted-foreground",
  indefinido: "bg-muted-foreground/40",
};

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}m`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

interface Props {
  atendentes: AtendenteStatus[];
  departamentos: Departamento[];
}

export function AtendentesList({ atendentes, departamentos: _deps }: Props) {
  const [statusFilter, setStatusFilter] = useState<string>("todos");
  const [busca, setBusca] = useState("");
  const [editing, setEditing] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return atendentes.filter((a) => {
      if (statusFilter !== "todos") {
        const s = a.atendente_status ?? "indefinido";
        if (s !== statusFilter) return false;
      }
      if (busca) {
        const q = busca.toLowerCase();
        if (
          !(a.nome || "").toLowerCase().includes(q) &&
          !(a.email || "").toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      return true;
    });
  }, [atendentes, statusFilter, busca]);

  const counts = useMemo(() => {
    const c = { online: 0, ausente: 0, pausa: 0, offline: 0, indefinido: 0 };
    for (const a of atendentes) {
      const s = (a.atendente_status ?? "indefinido") as keyof typeof c;
      c[s] = (c[s] || 0) + 1;
    }
    return c;
  }, [atendentes]);

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {(
          [
            ["online", "Online"],
            ["ausente", "Ausente"],
            ["pausa", "Em pausa"],
            ["offline", "Offline"],
            ["indefinido", "Sem status"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setStatusFilter(statusFilter === k ? "todos" : k)}
            className={cn(
              "rounded-lg border bg-card p-3 text-left transition hover:bg-accent",
              statusFilter === k && "ring-2 ring-primary/40"
            )}
          >
            <div className="flex items-center gap-2">
              <span className={cn("h-2 w-2 rounded-full", STATUS_DOT[k])} />
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {label}
              </span>
            </div>
            <p className="mt-1 text-2xl font-semibold">{counts[k] ?? 0}</p>
          </button>
        ))}
      </div>

      {/* Filtros */}
      <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-3">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome ou email…"
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 pl-8 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="todos">Todos status</option>
          <option value="online">Online</option>
          <option value="ausente">Ausente</option>
          <option value="pausa">Em pausa</option>
          <option value="offline">Offline</option>
          <option value="indefinido">Sem status</option>
        </select>
      </div>

      {/* Lista */}
      {filtered.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Nenhum atendente bate os filtros aplicados.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map((a) => {
            const statusKey = (a.atendente_status ??
              "indefinido") as keyof typeof STATUS_META;
            const meta = STATUS_META[statusKey];
            const ratio = a.ratio_capacidade;
            const ratioColor =
              ratio >= 1
                ? "text-red-600 dark:text-red-400"
                : ratio >= 0.7
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-emerald-600 dark:text-emerald-400";

            return (
              <Card key={a.user_id} className="overflow-hidden">
                <CardHeader className="space-y-2 pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      {a.image ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={a.image}
                          alt={a.nome ?? a.email ?? "atendente"}
                          className="size-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold uppercase">
                          {(a.nome || a.email || "?").trim().charAt(0)}
                        </div>
                      )}
                      <div className="min-w-0">
                        <CardTitle className="truncate text-base">
                          {a.nome || "—"}
                        </CardTitle>
                        <p className="truncate text-xs text-muted-foreground">
                          {a.email}
                        </p>
                      </div>
                    </div>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-medium",
                        meta.cls
                      )}
                    >
                      <span
                        className={cn(
                          "size-1.5 rounded-full",
                          STATUS_DOT[statusKey]
                        )}
                      />
                      {meta.label}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Capacidade</span>
                    <span className={cn("font-mono text-xs", ratioColor)}>
                      {a.count_atendimentos_abertos}/
                      {a.atendente_max_paralelos}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">
                      Última atividade
                    </span>
                    <span className="font-mono text-xs">
                      {formatRelative(a.atendente_status_at)}
                    </span>
                  </div>
                  {!a.is_active && (
                    <Badge variant="destructive" className="text-[10px]">
                      desativado
                    </Badge>
                  )}
                  <div className="flex flex-wrap gap-2 pt-2">
                    <CapacidadeEditor
                      userId={a.user_id}
                      currentMax={a.atendente_max_paralelos}
                      isEditing={editing === a.user_id}
                      onStartEdit={() => setEditing(a.user_id)}
                      onCancelEdit={() => setEditing(null)}
                      onSaved={() => setEditing(null)}
                    />
                    <Link
                      href={`/companies/1/members?user=${a.user_id}`}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                      title="Gerenciar perfis e role"
                    >
                      Perfis
                    </Link>
                    <Link
                      href={`/settings/departamentos?user=${a.user_id}`}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                      title="Gerenciar departamentos"
                    >
                      Departamentos
                    </Link>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CapacidadeEditor({
  userId,
  currentMax,
  isEditing,
  onStartEdit,
  onCancelEdit,
  onSaved,
}: {
  userId: string;
  currentMax: number;
  isEditing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaved: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState(String(currentMax));
  const [, startTransition] = useTransition();
  const [saving, setSaving] = useState(false);

  if (!isEditing) {
    return (
      <button
        type="button"
        onClick={onStartEdit}
        className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
      >
        <Settings2 className="size-3" />
        Capacidade
      </button>
    );
  }

  const submit = async () => {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 1 || n > 50) {
      alert("Capacidade deve estar entre 1 e 50");
      return;
    }
    setSaving(true);
    const res = await setMaxParalelosAction(userId, n);
    setSaving(false);
    if (res.ok) {
      onSaved();
      startTransition(() => router.refresh());
    } else {
      alert(res.error || "Erro ao salvar.");
    }
  };

  return (
    <div className="inline-flex items-center gap-1">
      <input
        type="number"
        min={1}
        max={50}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="h-7 w-16 rounded-md border border-input bg-transparent px-2 py-0.5 text-xs"
      />
      <Button size="sm" variant="outline" onClick={submit} disabled={saving}>
        Salvar
      </Button>
      <Button size="sm" variant="ghost" onClick={onCancelEdit}>
        Cancelar
      </Button>
    </div>
  );
}
