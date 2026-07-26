"use client";

import Link from "next/link";
import { Eye, MessageSquareWarning } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RowSemResposta } from "@/lib/dashboard-atendimento-api";

export function TabelaSemResposta({ rows }: { rows: RowSemResposta[] }) {
  return (
    <div className="rounded-lg border border-border/40 bg-card/40">
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-2">
        <div className="flex items-center gap-2">
          <MessageSquareWarning className="size-4 text-rose-400" />
          <h3 className="text-sm font-semibold uppercase tracking-wide">
            Sem resposta
          </h3>
          <Badge variant="outline" className="text-[10px]">
            {rows.length}
          </Badge>
        </div>
        <Link
          href="/atendimento?status=em_andamento"
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          ver todos →
        </Link>
      </div>
      {rows.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          ✅ Tudo em dia — atendentes respondendo no prazo.
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-border/20">
              <th className="px-3 py-1.5 text-left">Cliente</th>
              <th className="px-3 py-1.5 text-left">Atendente</th>
              <th className="px-3 py-1.5 text-right">Sem resposta</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/10 last:border-0 hover:bg-muted/10"
              >
                <td className="px-3 py-1.5 truncate max-w-[160px]" title={r.cliente_nome}>
                  {r.cliente_nome}
                </td>
                <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[120px]">
                  {r.assigned_to_user_id ? r.assigned_to_user_id.slice(0, 8) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <TempoSemResposta minutos={r.desde_ultima_min} />
                </td>
                <td className="px-1 py-1.5 text-right">
                  <Link
                    href={`/atendimento/${r.id}`}
                    className="inline-flex h-6 w-6 items-center justify-center rounded hover:bg-muted/30"
                    title="Abrir"
                  >
                    <Eye className="size-3" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TempoSemResposta({ minutos }: { minutos: number }) {
  let cls = "text-blue-300";
  if (minutos > 60) cls = "text-rose-400 font-medium";
  else if (minutos > 30) cls = "text-amber-400";

  const display =
    minutos < 60
      ? `${Math.round(minutos)}m`
      : `${Math.floor(minutos / 60)}h${String(Math.round(minutos % 60)).padStart(2, "0")}m`;

  return <span className={`font-mono ${cls}`}>{display}</span>;
}
