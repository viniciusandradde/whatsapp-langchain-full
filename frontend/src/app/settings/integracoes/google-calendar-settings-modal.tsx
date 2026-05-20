"use client";

import { useState, useTransition } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { GoogleCalendarConfig } from "@/lib/api";

import { updateAprovadorTelefoneAction } from "./actions";

interface Props {
  config: GoogleCalendarConfig;
  onClose: (updated: GoogleCalendarConfig | null) => void;
}

/**
 * Modal de configuração avançada do Google Calendar.
 *
 * Hoje cobre só `aprovador_telefone` (campo do storage legacy
 * `empresa_calendar_config` que não cabe na section unificada).
 * Quando outros campos ganharem UI, entram aqui.
 */
export function GoogleCalendarSettingsModal({ config, onClose }: Props) {
  const [aprovador, setAprovador] = useState(config.aprovador_telefone ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    startTransition(async () => {
      const r = await updateAprovadorTelefoneAction(aprovador.trim());
      setSaving(false);
      if (r.ok) {
        onClose({ ...config, aprovador_telefone: aprovador.trim() });
      } else {
        setError(r.error);
      }
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(null)}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">Google Calendar — Avançado</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(null)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-4">
          <div>
            <label className="mb-1 block text-xs font-medium">
              Telefone do aprovador
            </label>
            <input
              type="tel"
              value={aprovador}
              onChange={(e) => setAprovador(e.target.value)}
              placeholder="+5567999999999"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Quando o agente IA criar um evento que exige aprovação humana,
              envia notificação WhatsApp pra este número. Deixe vazio pra
              auto-aprovar.
            </p>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose(null)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Salvar
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
