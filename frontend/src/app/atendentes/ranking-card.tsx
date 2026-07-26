/**
 * Sprint J — Card de ranking dos atendentes (last N days).
 * Mostra top atendentes por count_resolvidos com avg tempo de resolução.
 */

import { Trophy } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AtendenteRankingItem } from "@/lib/api";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const min = seconds / 60;
  if (min < 60) return `${Math.round(min)}min`;
  const h = min / 60;
  return `${h.toFixed(1)}h`;
}

interface Props {
  items: AtendenteRankingItem[];
  dias: number;
}

export function RankingCard({ items, dias }: Props) {
  if (items.length === 0) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Trophy className="size-4 text-amber-500" />
          <CardTitle className="text-base">
            Ranking — últimos {dias} dias
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="py-1 pr-2 text-left font-normal">#</th>
              <th className="py-1 pr-2 text-left font-normal">Atendente</th>
              <th className="py-1 pr-2 text-right font-normal">Resolvidos</th>
              <th className="py-1 pr-2 text-right font-normal">
                Tempo médio
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, idx) => (
              <tr key={it.user_id} className="border-b last:border-0">
                <td className="py-1.5 pr-2 font-mono text-xs">
                  {idx + 1}
                </td>
                <td className="py-1.5 pr-2">
                  <div className="flex items-center gap-2">
                    {it.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={it.image}
                        alt={it.nome ?? ""}
                        className="size-6 rounded-full object-cover"
                      />
                    ) : (
                      <span className="flex size-6 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold uppercase">
                        {(it.nome || "?").charAt(0)}
                      </span>
                    )}
                    <span>{it.nome || "—"}</span>
                  </div>
                </td>
                <td className="py-1.5 pr-2 text-right font-mono">
                  {it.resolvidos}
                </td>
                <td className="py-1.5 pr-2 text-right font-mono text-xs">
                  {formatDuration(it.avg_segundos_resolucao)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
