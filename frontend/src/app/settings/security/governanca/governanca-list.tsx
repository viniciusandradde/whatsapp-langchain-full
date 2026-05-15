"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AuditGovernancaEvent } from "@/lib/api";

interface Props {
  items: AuditGovernancaEvent[];
  limit: number;
  offset: number;
  filters: Record<string, string | undefined>;
}

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  "perfil.sync": { label: "Perfis atualizados", color: "bg-blue-500/15 text-blue-700 dark:text-blue-300" },
  "depto.sync": { label: "Departamentos atualizados", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
  "role.change": { label: "Role legacy alterada", color: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
  "superadmin.grant": { label: "Superadmin concedido", color: "bg-red-500/15 text-red-700 dark:text-red-300" },
  "superadmin.revoke": { label: "Superadmin revogado", color: "bg-orange-500/15 text-orange-700 dark:text-orange-300" },
  "member.add": { label: "Membro adicionado", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
  "member.remove": { label: "Membro removido", color: "bg-red-500/15 text-red-700 dark:text-red-300" },
  "member.disable": { label: "Membro desativado", color: "bg-orange-500/15 text-orange-700 dark:text-orange-300" },
  "member.enable": { label: "Membro reativado", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
};

function buildHref(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) sp.set(k, v);
  });
  const qs = sp.toString();
  return qs ? `?${qs}` : "?";
}

function diffSummary(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null
): string {
  if (!before && !after) return "—";
  // Heurística: lê arrays comuns (perfil_ids, departamento_ids)
  for (const key of ["perfil_ids", "departamento_ids"]) {
    const b = (before as Record<string, unknown> | null)?.[key];
    const a = (after as Record<string, unknown> | null)?.[key];
    if (Array.isArray(b) && Array.isArray(a)) {
      const removed = b.filter((x) => !a.includes(x));
      const added = a.filter((x) => !b.includes(x));
      const parts: string[] = [];
      if (added.length) parts.push(`+ ${added.join(",")}`);
      if (removed.length) parts.push(`- ${removed.join(",")}`);
      return parts.length ? parts.join(" ") : "(sem mudança)";
    }
  }
  return JSON.stringify({ before, after }).slice(0, 80);
}

export function GovernancaList({ items, limit, offset, filters }: Props) {
  return (
    <div className="space-y-4">
      {/* Filtros simples (URL params) */}
      <div className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-muted/20 p-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">
            Filtrar por user (target)
          </label>
          <form className="flex gap-2">
            <input
              type="text"
              name="target_user_id"
              defaultValue={filters.target_user_id ?? ""}
              placeholder="user_id"
              className="rounded-md border border-input bg-background px-2 py-1 text-xs"
            />
            <input
              type="text"
              name="action"
              defaultValue={filters.action ?? ""}
              placeholder="action (ex: perfil.sync)"
              className="rounded-md border border-input bg-background px-2 py-1 text-xs"
            />
            <Button type="submit" size="sm" variant="outline">
              Filtrar
            </Button>
            {(filters.target_user_id || filters.action || filters.actor_user_id) && (
              <Link href="?">
                <Button type="button" size="sm" variant="ghost">
                  Limpar
                </Button>
              </Link>
            )}
          </form>
        </div>
        <p className="ml-auto text-xs text-muted-foreground">
          {items.length} eventos {offset > 0 ? `(offset ${offset})` : ""}
        </p>
      </div>

      {items.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Nenhum evento de governança ainda.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Quando</th>
                <th className="px-3 py-2 font-medium">Ação</th>
                <th className="px-3 py-2 font-medium">Quem fez</th>
                <th className="px-3 py-2 font-medium">Quem foi afetado</th>
                <th className="px-3 py-2 font-medium">Mudança</th>
                <th className="px-3 py-2 font-medium">IP</th>
              </tr>
            </thead>
            <tbody>
              {items.map((ev) => {
                const meta = ACTION_LABELS[ev.action] ?? {
                  label: ev.action,
                  color: "bg-muted text-muted-foreground",
                };
                return (
                  <tr key={ev.id} className="border-t border-border">
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      {ev.created_at
                        ? new Date(ev.created_at).toLocaleString("pt-BR")
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className={`${meta.color} text-[10px]`}>
                        {meta.label}
                      </Badge>
                    </td>
                    <td className="px-3 py-2">
                      <code className="text-[10px]">{ev.actor_user_id}</code>
                    </td>
                    <td className="px-3 py-2">
                      {ev.target_user_id ? (
                        <code className="text-[10px]">{ev.target_user_id}</code>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">
                          —
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
                        {diffSummary(ev.payload_before, ev.payload_after)}
                      </code>
                    </td>
                    <td className="px-3 py-2 text-[10px] text-muted-foreground font-mono">
                      {ev.ip_address ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginação */}
      <div className="flex items-center justify-between">
        <Link
          href={buildHref({
            ...filters,
            offset: String(Math.max(0, offset - limit)),
          })}
        >
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={offset === 0}
          >
            <ChevronLeft className="size-4" />
            Anterior
          </Button>
        </Link>
        <span className="text-xs text-muted-foreground">
          Mostrando {offset + 1} – {offset + items.length}
        </span>
        <Link
          href={buildHref({
            ...filters,
            offset: String(offset + limit),
          })}
        >
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={items.length < limit}
          >
            Próximo
            <ChevronRight className="size-4" />
          </Button>
        </Link>
      </div>
    </div>
  );
}
