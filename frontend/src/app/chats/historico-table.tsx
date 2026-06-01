"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { HistoricoRow } from "@/lib/api";

import { HistoricoDetalheDrawer } from "./historico-detalhe-drawer";

type SP = Record<string, string | string[] | undefined>;

const STATUS_STYLE: Record<string, string> = {
  aguardando:
    "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40",
  em_andamento:
    "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/40",
  resolvido:
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
  abandonado: "bg-muted text-muted-foreground border-muted",
};
const STATUS_LABEL: Record<string, string> = {
  aguardando: "Aguardando",
  em_andamento: "Em andamento",
  resolvido: "Resolvido",
  abandonado: "Abandonado",
};
const PRIORIDADE_STYLE: Record<string, string> = {
  urgente: "text-red-600 dark:text-red-400",
  alta: "text-orange-600 dark:text-orange-400",
  media: "text-blue-600 dark:text-blue-400",
  baixa: "text-muted-foreground",
};

function fmtDateTime(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuracao(seg: number | null): string {
  if (seg == null) return "—";
  if (seg < 60) return `${seg}s`;
  const min = Math.floor(seg / 60);
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  return `${h}h ${min % 60}min`;
}

function csatColor(nota: number | null): string {
  if (nota == null) return "text-muted-foreground";
  if (nota >= 9) return "text-emerald-600 dark:text-emerald-400 font-semibold";
  if (nota >= 7) return "text-amber-600 dark:text-amber-400 font-semibold";
  return "text-red-600 dark:text-red-400 font-semibold";
}

const COLS: { key: string; label: string; sortable?: boolean; cls?: string }[] = [
  { key: "protocolo", label: "Protocolo", sortable: true },
  { key: "cliente", label: "Cliente" },
  { key: "canal", label: "Canal", cls: "hidden lg:table-cell" },
  { key: "atendente", label: "Atendente", cls: "hidden xl:table-cell" },
  { key: "departamento", label: "Depto", cls: "hidden xl:table-cell" },
  { key: "status", label: "Status", sortable: true },
  { key: "created_at", label: "Início", sortable: true },
  { key: "duracao", label: "Duração", sortable: true, cls: "hidden md:table-cell" },
  { key: "nota", label: "CSAT", sortable: true, cls: "text-center" },
];

export function HistoricoTable({
  rows,
  total,
  page,
  limit,
  current,
}: {
  rows: HistoricoRow[];
  total: number;
  page: number;
  limit: number;
  current: SP;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<HistoricoRow | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const sortField = (Array.isArray(current.sort_field)
    ? current.sort_field[0]
    : current.sort_field) ?? "created_at";
  const sortOrder = (Array.isArray(current.sort_order)
    ? current.sort_order[0]
    : current.sort_order) ?? "desc";

  function pushParams(patch: Record<string, string>) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(current)) {
      if (v === undefined) continue;
      if (Array.isArray(v)) for (const x of v) p.append(k, x);
      else p.set(k, v);
    }
    for (const [k, v] of Object.entries(patch)) p.set(k, v);
    router.push(`/chats?${p.toString()}`);
  }

  function sortBy(key: string) {
    const next = sortField === key && sortOrder === "desc" ? "asc" : "desc";
    pushParams({ sort_field: key, sort_order: next, page: "1" });
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              {COLS.map((c) => (
                <th
                  key={c.key}
                  className={`px-3 py-2 font-medium ${c.cls ?? ""} ${
                    c.sortable ? "cursor-pointer select-none hover:text-foreground" : ""
                  }`}
                  onClick={c.sortable ? () => sortBy(c.key) : undefined}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {c.sortable && sortField === c.key && (
                      sortOrder === "desc" ? (
                        <ArrowDown className="h-3 w-3" />
                      ) : (
                        <ArrowUp className="h-3 w-3" />
                      )
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                onClick={() => setSelected(r)}
                className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
              >
                <td className="px-3 py-2 font-mono text-xs">{r.protocolo ?? `#${r.id}`}</td>
                <td className="px-3 py-2">
                  <div className="font-medium">{r.cliente_nome ?? "—"}</div>
                  <div className="text-xs text-muted-foreground">
                    {r.cliente_telefone ?? ""}
                  </div>
                </td>
                <td className="px-3 py-2 hidden lg:table-cell text-muted-foreground">
                  {r.conexao_nome ?? r.conexao_numero ?? "—"}
                </td>
                <td className="px-3 py-2 hidden xl:table-cell text-muted-foreground">
                  {r.atendente_nome ?? <span className="italic">IA</span>}
                </td>
                <td className="px-3 py-2 hidden xl:table-cell text-muted-foreground">
                  {r.departamento_nome ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <Badge
                    variant="outline"
                    className={STATUS_STYLE[r.status] ?? ""}
                  >
                    {STATUS_LABEL[r.status] ?? r.status}
                  </Badge>
                  {r.prioridade && (
                    <span
                      className={`ml-1 text-xs ${PRIORIDADE_STYLE[r.prioridade] ?? ""}`}
                    >
                      • {r.prioridade}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">
                  {fmtDateTime(r.created_at)}
                </td>
                <td className="px-3 py-2 hidden md:table-cell whitespace-nowrap text-muted-foreground">
                  {fmtDuracao(r.duracao_seg)}
                </td>
                <td className={`px-3 py-2 text-center ${csatColor(r.nota_csat)}`}>
                  {r.nota_csat ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Paginação */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {total.toLocaleString("pt-BR")} atendimento(s) · página {page} de{" "}
          {totalPages}
        </span>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => pushParams({ page: String(page - 1) })}
            className="inline-flex items-center rounded-md border px-2 py-1 disabled:opacity-40 hover:bg-muted"
          >
            <ChevronLeft className="h-4 w-4" /> Anterior
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => pushParams({ page: String(page + 1) })}
            className="inline-flex items-center rounded-md border px-2 py-1 disabled:opacity-40 hover:bg-muted"
          >
            Próxima <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {selected && (
        <HistoricoDetalheDrawer
          row={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
