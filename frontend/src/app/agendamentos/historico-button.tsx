"use client";

import { useState } from "react";
import { History, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getAgendamentoHistorico, type AgendamentoHistorico } from "@/lib/api";

const ACTION_LABEL: Record<string, string> = {
  created: "Criado",
  approved: "Aprovado",
  rejected: "Rejeitado",
  rescheduled: "Reagendado",
  cancelled: "Cancelado",
  sync_drift: "Sync Google",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function HistoricoButton({ agendamentoId }: { agendamentoId: number }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AgendamentoHistorico[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleOpen() {
    setOpen(true);
    if (items === null) {
      setLoading(true);
      try {
        const r = await getAgendamentoHistorico(agendamentoId);
        setItems(r.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao carregar histórico.");
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <>
      <Button variant="ghost" size="sm" onClick={handleOpen} title="Ver histórico">
        <History className="size-3.5" />
      </Button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-xl max-h-[80vh] overflow-auto rounded-lg bg-card p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">
                Histórico do agendamento #{agendamentoId}
              </h3>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setOpen(false)}
                aria-label="Fechar"
              >
                <X className="size-4" />
              </Button>
            </div>

            {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}

            {error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {items && items.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Sem entradas no histórico ainda.
              </p>
            )}

            {items && items.length > 0 && (
              <ol className="space-y-3">
                {items.map((h) => (
                  <li
                    key={h.id}
                    className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3 text-sm"
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="font-medium">
                        {ACTION_LABEL[h.action] ?? h.action}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(h.at)}
                      </span>
                    </div>
                    {h.actor_user_id && (
                      <p className="text-xs text-muted-foreground">
                        por {h.actor_user_id.slice(0, 8)}…
                      </p>
                    )}
                    {Object.keys(h.payload_diff).length > 0 && (
                      <pre className="mt-2 overflow-x-auto rounded bg-obsidian-900 p-2 text-[10px] text-muted-foreground">
                        {JSON.stringify(h.payload_diff, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </>
  );
}
