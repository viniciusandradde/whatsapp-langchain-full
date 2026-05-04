import { CalendarDays } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAgendamentos, type Agendamento } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { HistoricoButton } from "./historico-button";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<
  Agendamento["status"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  pendente: "secondary",
  confirmado: "default",
  cancelado: "destructive",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR");
}

/**
 * Página /agendamentos — lista source-of-truth interno (S2+S5).
 *
 * Default: agendamentos da empresa ativa nos últimos 7d → +30d.
 * Cada row tem botão "Histórico" abrindo modal com audit trail (S5).
 */
export default async function AgendamentosPage() {
  await requireSession();

  let items: Agendamento[] = [];
  let loadError: string | null = null;
  try {
    const r = await getAgendamentos({ limit: 200 });
    items = r.items;
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Erro desconhecido ao carregar agendamentos.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <CalendarDays className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Agendamentos</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {items.length} agendamento{items.length === 1 ? "" : "s"} em -7d → +30d
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadError ? (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
              {loadError}
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum agendamento no período. Eventos criados pelo agente via
              WhatsApp aparecem aqui.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
              <table className="w-full text-sm">
                <thead className="bg-white/[0.02] text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Quando</th>
                    <th className="px-3 py-2 font-medium">Assunto</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Aprovação</th>
                    <th className="px-3 py-2 font-medium">Calendar</th>
                    <th className="px-3 py-2 font-medium">Google ID</th>
                    <th className="px-3 py-2 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((a) => (
                    <tr key={a.id} className="border-t border-white/[0.06]">
                      <td className="px-3 py-2 text-xs whitespace-nowrap">
                        {formatDateTime(a.data_inicio)}
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{a.summary}</div>
                        {a.descricao && (
                          <div className="text-xs text-muted-foreground line-clamp-1">
                            {a.descricao}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={STATUS_VARIANT[a.status]}>
                          {a.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {a.aprovado ? (
                          <span className="text-emerald-400">aprovado</span>
                        ) : a.gestor_notificado ? (
                          <span className="text-amber-400">aguardando</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {a.calendar_id}
                      </td>
                      <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">
                        {a.evento_id_externo
                          ? a.evento_id_externo.slice(0, 12) + "…"
                          : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <HistoricoButton agendamentoId={a.id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
