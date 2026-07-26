"use client";

import Link from "next/link";
import { Eye, Hourglass } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RowAguardando } from "@/lib/dashboard-atendimento-api";

export function TabelaAguardando({ rows }: { rows: RowAguardando[] }) {
  return (
    <div className="rounded-lg border border-border/40 bg-card/40">
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-2">
        <div className="flex items-center gap-2">
          <Hourglass className="size-4 text-amber-400" />
          <h3 className="text-sm font-semibold uppercase tracking-wide">
            Aguardando atendimento
          </h3>
          <Badge variant="outline" className="text-[10px]">
            {rows.length}
          </Badge>
        </div>
        <Link
          href="/atendimento?status=aguardando"
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          ver todos →
        </Link>
      </div>
      {rows.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          🎉 Fila vazia! Nenhum cliente aguardando.
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-border/20">
              <th className="px-3 py-1.5 text-left">Cliente</th>
              <th className="px-3 py-1.5 text-left">Departamento</th>
              <th className="px-3 py-1.5 text-right">Espera</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/10 last:border-0 hover:bg-muted/10"
              >
                <td className="px-3 py-1.5 truncate max-w-[180px]" title={r.cliente_nome}>
                  {r.cliente_nome}
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">
                  {r.departamento_nome || "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <TempoEspera minutos={r.espera_min} />
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

function TempoEspera({ minutos }: { minutos: number }) {
  let cls = "text-muted-foreground";
  if (minutos > 30) cls = "text-rose-400 font-medium";
  else if (minutos > 10) cls = "text-amber-400";
  else if (minutos > 5) cls = "text-blue-300";

  const display =
    minutos < 1
      ? "agora"
      : minutos < 60
        ? `${Math.round(minutos)}m`
        : `${Math.floor(minutos / 60)}h${String(Math.round(minutos % 60)).padStart(2, "0")}m`;

  return <span className={`font-mono ${cls}`}>{display}</span>;
}
