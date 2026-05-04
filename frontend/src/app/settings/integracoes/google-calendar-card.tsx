"use client";

import { useState, useTransition } from "react";
import { Calendar, CheckCircle2, ExternalLink, Save, Unplug } from "lucide-react";

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
  updateAprovadorTelefoneAction,
} from "./actions";

interface Props {
  config: GoogleCalendarConfig | null;
}

export function GoogleCalendarCard({ config }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [aprovador, setAprovador] = useState(config?.aprovador_telefone ?? "");
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
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

  function handleSaveAprovador() {
    setError(null);
    setSavedMsg(null);
    startTransition(async () => {
      const r = await updateAprovadorTelefoneAction(aprovador.trim());
      if (!r.ok) {
        setError(r.error);
      } else {
        setSavedMsg(
          aprovador.trim()
            ? "Telefone do aprovador salvo."
            : "Telefone removido (fluxo de aprovação desativado)."
        );
      }
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
          <>
            <div className="space-y-1.5 text-sm">
              <Row label="Conta Google" value={config.google_email ?? "—"} mono />
              <Row label="Calendário" value={config.calendar_id} mono />
              <Row label="Fuso horário" value={config.timezone} />
              <Row
                label="Conectado em"
                value={new Date(config.created_at).toLocaleString("pt-BR")}
              />
            </div>

            <div className="space-y-2 rounded-md border border-white/[0.06] bg-white/[0.02] p-3">
              <label className="text-sm font-medium" htmlFor="aprovador">
                Telefone do gestor aprovador (opcional)
              </label>
              <p className="text-xs text-muted-foreground">
                Se preenchido + regra <code>requer_aprovacao</code> ativa,
                o sistema manda WhatsApp pra esse número antes de criar
                o evento. Formato E.164 (<code>+5567984249725</code>).
              </p>
              <div className="flex items-center gap-2">
                <input
                  id="aprovador"
                  type="text"
                  value={aprovador}
                  onChange={(e) => setAprovador(e.target.value)}
                  placeholder="+55..."
                  className="flex-1 rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5 text-sm font-mono"
                  disabled={isPending}
                />
                <Button
                  size="sm"
                  onClick={handleSaveAprovador}
                  disabled={isPending}
                >
                  <Save className="size-3.5" />
                  Salvar
                </Button>
              </div>
              {savedMsg && (
                <p className="text-xs text-emerald-400">{savedMsg}</p>
              )}
            </div>
          </>
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
