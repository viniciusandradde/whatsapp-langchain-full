"use client";

import { useState, useTransition } from "react";
import { Calendar, CheckCircle2, ExternalLink, Unplug } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { GoogleCalendarConfig } from "@/lib/api";

import {
  disconnectGoogleCalendarAction,
  startGoogleCalendarOAuthAction,
} from "./actions";

interface Props {
  config: GoogleCalendarConfig | null;
}

export function GoogleCalendarCard({ config }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleConnect() {
    setError(null);
    startTransition(async () => {
      const r = await startGoogleCalendarOAuthAction();
      if (!r.ok) {
        setError(r.error);
        return;
      }
      // Redireciona o navegador pro Google OAuth — o callback retorna
      // pra /settings/integracoes?google_calendar=ok.
      window.location.href = r.url;
    });
  }

  function handleDisconnect() {
    if (!confirm("Desconectar o Google Calendar? O agente para de agendar.")) {
      return;
    }
    setError(null);
    startTransition(async () => {
      const r = await disconnectGoogleCalendarAction();
      if (!r.ok) setError(r.error);
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <Calendar className="h-6 w-6 text-brand-primary" />
            <div>
              <CardTitle>Google Calendar</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Permite que o agente proponha horários e crie eventos.
              </p>
            </div>
          </div>
          {config?.ativo && (
            <Badge variant="default" className="gap-1">
              <CheckCircle2 className="size-3" />
              Conectado
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {config ? (
          <div className="space-y-1.5 text-sm">
            <Row label="Conta Google" value={config.google_email ?? "—"} mono />
            <Row label="Calendário" value={config.calendar_id} mono />
            <Row label="Fuso horário" value={config.timezone} />
            <Row
              label="Conectado em"
              value={new Date(config.created_at).toLocaleString("pt-BR")}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Nenhuma conta conectada. Conecte uma conta Google pra que o
            agente leia disponibilidade e crie eventos automaticamente
            quando o cliente confirmar um horário.
          </p>
        )}

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          {config ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDisconnect}
              disabled={isPending}
            >
              <Unplug className="size-3.5" />
              Desconectar
            </Button>
          ) : (
            <Button onClick={handleConnect} disabled={isPending}>
              <ExternalLink className="size-3.5" />
              {isPending ? "Abrindo Google…" : "Conectar Google Calendar"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "truncate font-mono text-xs" : "truncate"}>
        {value}
      </span>
    </div>
  );
}
