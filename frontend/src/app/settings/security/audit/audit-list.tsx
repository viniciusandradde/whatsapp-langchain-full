"use client";

import Link from "next/link";
import { useState } from "react";
import { Filter } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AuditLog } from "@/lib/api";

interface Props {
  items: AuditLog[];
  limit: number;
  offset: number;
  filters: {
    entity_type?: string;
    action?: string;
    user_id?: string;
  };
}

export function AuditList({ items, limit, offset, filters }: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // URL pra filtros — atualiza search params
  function buildHref(next: Partial<Props["filters"]> & { offset?: number }) {
    const merged = { ...filters, ...next };
    const params = new URLSearchParams();
    if (merged.entity_type) params.set("entity_type", merged.entity_type);
    if (merged.action) params.set("action", merged.action);
    if (merged.user_id) params.set("user_id", merged.user_id);
    if (next.offset != null && next.offset > 0)
      params.set("offset", String(next.offset));
    const q = params.toString();
    return `/settings/security/audit${q ? "?" + q : ""}`;
  }

  const hasNext = items.length === limit;
  const hasPrev = offset > 0;

  return (
    <div className="space-y-4">
      {/* Filtros via form GET — sem JS, recarrega página */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="size-4" /> Filtros
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap gap-3" action="/settings/security/audit">
            <input
              type="text"
              name="entity_type"
              placeholder="entity_type (cliente, perfil, ...)"
              defaultValue={filters.entity_type ?? ""}
              className="flex h-9 w-56 rounded-md border border-input bg-background px-3 text-sm"
            />
            <input
              type="text"
              name="action"
              placeholder="action (cliente.update, ...)"
              defaultValue={filters.action ?? ""}
              className="flex h-9 w-56 rounded-md border border-input bg-background px-3 text-sm"
            />
            <input
              type="text"
              name="user_id"
              placeholder="user_id"
              defaultValue={filters.user_id ?? ""}
              className="flex h-9 w-56 rounded-md border border-input bg-background px-3 text-sm font-mono text-xs"
            />
            <Button type="submit" size="sm">
              Aplicar
            </Button>
            {(filters.entity_type || filters.action || filters.user_id) && (
              <Link href="/settings/security/audit">
                <Button type="button" size="sm" variant="ghost">
                  Limpar
                </Button>
              </Link>
            )}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {items.length} registro(s) (offset {offset})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum registro com esses filtros.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {items.map((it) => (
                <li
                  key={it.id}
                  className="cursor-pointer p-3 hover:bg-white/[0.02]"
                  onClick={() =>
                    setExpandedId(expandedId === it.id ? null : it.id)
                  }
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {it.action}
                        </Badge>
                        <span className="text-sm font-medium">
                          {it.entity_type}
                          {it.entity_id ? ` #${it.entity_id}` : ""}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(it.at).toLocaleString("pt-BR")} ·{" "}
                        {it.user_id ? (
                          <code className="font-mono text-[10px]">
                            {it.user_id.slice(0, 8)}…
                          </code>
                        ) : (
                          <span className="italic">sistema</span>
                        )}
                        {it.ip ? ` · ${it.ip}` : ""}
                      </p>
                    </div>
                  </div>
                  {expandedId === it.id && (
                    <pre className="mt-3 max-h-80 overflow-auto rounded bg-white/[0.04] p-3 font-mono text-[11px]">
                      {JSON.stringify(it.payload_diff, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Link href={hasPrev ? buildHref({ offset: Math.max(0, offset - limit) }) : "#"}>
          <Button size="sm" variant="ghost" disabled={!hasPrev}>
            ← Anterior
          </Button>
        </Link>
        <Link href={hasNext ? buildHref({ offset: offset + limit }) : "#"}>
          <Button size="sm" variant="ghost" disabled={!hasNext}>
            Próximo →
          </Button>
        </Link>
      </div>
    </div>
  );
}
