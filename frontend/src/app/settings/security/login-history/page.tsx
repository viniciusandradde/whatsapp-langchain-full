import { Activity, AlertTriangle, CheckCircle2, ShieldOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getLoginEvents, type LoginEvent } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const EVENT_LABEL: Record<LoginEvent["event_type"], string> = {
  login_success: "Login OK",
  login_failed: "Login falhou",
  logout: "Logout",
  password_reset_requested: "Reset solicitado",
  password_changed: "Senha alterada",
  session_blocked_disabled: "Bloqueado (desativado)",
};

function eventIcon(type: LoginEvent["event_type"]) {
  if (type === "login_success") return <CheckCircle2 className="size-4 text-emerald-400" />;
  if (type === "login_failed") return <AlertTriangle className="size-4 text-amber-400" />;
  if (type === "session_blocked_disabled")
    return <ShieldOff className="size-4 text-rose-400" />;
  return <Activity className="size-4 text-muted-foreground" />;
}

function eventVariant(
  type: LoginEvent["event_type"]
): "default" | "secondary" | "destructive" | "outline" {
  if (type === "login_failed" || type === "session_blocked_disabled")
    return "destructive";
  if (type === "login_success") return "default";
  return "outline";
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

function truncateUserAgent(ua: string | null): string {
  if (!ua) return "—";
  // Pega só o "browser/version" pra evitar ocupar a linha inteira.
  // Heurística simples: pega primeira parte significativa.
  const match = ua.match(/(?:Chrome|Firefox|Safari|Edge|Edg|Opera)\/[\d.]+/);
  return match ? match[0] : ua.slice(0, 40) + (ua.length > 40 ? "…" : "");
}

export default async function LoginHistoryPage() {
  await requireSession();
  const { events } = await getLoginEvents({ limit: 200 });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Activity className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Histórico de acesso</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Últimas {events.length} tentativas
          </CardTitle>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum evento registrado. Tentativas de login passarão a aparecer aqui.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
              <table className="w-full text-sm">
                <thead className="bg-white/[0.02] text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Quando</th>
                    <th className="px-3 py-2 font-medium">Evento</th>
                    <th className="px-3 py-2 font-medium">User</th>
                    <th className="px-3 py-2 font-medium">IP</th>
                    <th className="px-3 py-2 font-medium">Browser</th>
                    <th className="px-3 py-2 font-medium">Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} className="border-t border-white/[0.06]">
                      <td className="px-3 py-2 text-xs whitespace-nowrap">
                        {formatDateTime(e.created_at)}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          {eventIcon(e.event_type)}
                          <Badge variant={eventVariant(e.event_type)}>
                            {EVENT_LABEL[e.event_type]}
                          </Badge>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-xs">
                        <div>{e.email ?? "—"}</div>
                        {e.user_id && (
                          <div className="font-mono text-[10px] text-muted-foreground">
                            {e.user_id.slice(0, 8)}…
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {e.ip_address ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {truncateUserAgent(e.user_agent)}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {e.reason ?? "—"}
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
