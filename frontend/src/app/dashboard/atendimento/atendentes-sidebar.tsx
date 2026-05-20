"use client";

import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { AtendentesPayload } from "@/lib/dashboard-atendimento-api";

const AVATAR_COLORS = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-pink-500",
  "bg-violet-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-lime-500",
];

function avatarColor(nome: string): string {
  const hash = Array.from(nome).reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function iniciais(nome: string): string {
  const parts = nome.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function AtendentesSidebar({
  atendentes,
}: {
  atendentes: AtendentesPayload;
}) {
  const online = atendentes.items.filter((a) => a.status === "online");
  const offline = atendentes.items.filter((a) => a.status !== "online");

  return (
    <div className="rounded-lg border border-border/40 bg-card/40 p-3 xl:sticky xl:top-4 xl:h-[calc(100vh-2rem)]">
      <div className="mb-3 flex items-center gap-2">
        <Users className="size-4 text-muted-foreground" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Atendentes ({atendentes.total})
        </h3>
      </div>

      <div className="space-y-3 overflow-y-auto xl:max-h-[calc(100vh-7rem)]">
        <Section
          title="Online"
          count={online.length}
          color="bg-emerald-500"
          items={online}
          emptyText="Ninguém online no momento"
        />
        <Section
          title="Offline"
          count={offline.length}
          color="bg-zinc-500"
          items={offline}
          emptyText="Todos online ✨"
        />
      </div>
    </div>
  );
}

function Section({
  title,
  count,
  color,
  items,
  emptyText,
}: {
  title: string;
  count: number;
  color: string;
  items: AtendentesPayload["items"];
  emptyText: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between border-b border-border/20 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className={`size-2 rounded-full ${color}`} />
          {title}
        </span>
        <span>{count}</span>
      </div>
      {items.length === 0 ? (
        <p className="px-1 py-2 text-[11px] text-muted-foreground italic">
          {emptyText}
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((a) => (
            <li
              key={a.user_id}
              className="flex items-center gap-2 rounded-md px-1.5 py-1 text-xs hover:bg-muted/20"
              title={a.email || a.nome}
            >
              <span
                className={`flex size-6 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold text-white ${avatarColor(a.nome)}`}
              >
                {iniciais(a.nome)}
              </span>
              <span className="flex-1 truncate">{a.nome}</span>
              {a.atendimentos_abertos > 0 && (
                <Badge
                  variant="outline"
                  className="ml-1 h-4 px-1.5 text-[9px]"
                  title={`${a.atendimentos_abertos} atendimentos abertos`}
                >
                  {a.atendimentos_abertos}
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
