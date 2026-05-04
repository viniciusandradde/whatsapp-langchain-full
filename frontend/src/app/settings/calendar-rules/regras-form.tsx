"use client";

import { useState, useTransition } from "react";
import { CalendarCog, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CalendarRegras } from "@/lib/api";

import { saveCalendarRegrasAction } from "./actions";

interface Props {
  initial: CalendarRegras;
}

const DIAS = [
  { v: 1, label: "Seg" },
  { v: 2, label: "Ter" },
  { v: 3, label: "Qua" },
  { v: 4, label: "Qui" },
  { v: 5, label: "Sex" },
  { v: 6, label: "Sáb" },
  { v: 7, label: "Dom" },
];

export function RegrasForm({ initial }: Props) {
  const [horaInicio, setHoraInicio] = useState(initial.hora_inicio);
  const [horaFim, setHoraFim] = useState(initial.hora_fim);
  const [antecedencia, setAntecedencia] = useState(
    initial.antecedencia_minima_minutos
  );
  const [diasSemana, setDiasSemana] = useState<number[]>(
    initial.dias_semana_permitidos
  );
  const [diasBloqueadosStr, setDiasBloqueadosStr] = useState(
    initial.dias_bloqueados.join(", ")
  );
  const [requerAprovacao, setRequerAprovacao] = useState(initial.requer_aprovacao);

  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function toggleDia(v: number) {
    setDiasSemana((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v].sort()
    );
  }

  function handleSave() {
    setError(null);
    setSavedMsg(null);

    // Parse dias bloqueados (CSV "2026-05-08, 2026-05-09")
    const dias_bloqueados = diasBloqueadosStr
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    startTransition(async () => {
      const r = await saveCalendarRegrasAction({
        hora_inicio: horaInicio,
        hora_fim: horaFim,
        antecedencia_minima_minutos: antecedencia,
        dias_semana_permitidos: diasSemana,
        dias_bloqueados,
        requer_aprovacao: requerAprovacao,
      });
      if (!r.ok) setError(r.error);
      else setSavedMsg("Regras salvas. Próximos agendamentos já aplicam.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <CalendarCog className="h-6 w-6 text-brand-primary" />
          <CardTitle>Regras de agendamento</CardTitle>
        </div>
        <p className="text-xs text-muted-foreground">
          Aplicadas em <code>find_free_slots</code> (sugestões) e
          <code>create_event</code> (rejeição antes de chamar Google).
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Janela horária */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium" htmlFor="hi">
              Hora início (HH:MM)
            </label>
            <input
              id="hi"
              type="time"
              value={horaInicio}
              onChange={(e) => setHoraInicio(e.target.value)}
              className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm font-mono"
              disabled={isPending}
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="hf">
              Hora fim (HH:MM)
            </label>
            <input
              id="hf"
              type="time"
              value={horaFim}
              onChange={(e) => setHoraFim(e.target.value)}
              className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm font-mono"
              disabled={isPending}
            />
          </div>
        </div>

        {/* Antecedência */}
        <div>
          <label className="text-sm font-medium" htmlFor="ant">
            Antecedência mínima (minutos)
          </label>
          <input
            id="ant"
            type="number"
            min={0}
            value={antecedencia}
            onChange={(e) => setAntecedencia(Number(e.target.value))}
            className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm"
            disabled={isPending}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Cliente não pode agendar pra menos que isso a partir de agora.
          </p>
        </div>

        {/* Dias da semana */}
        <div>
          <span className="text-sm font-medium">Dias permitidos</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {DIAS.map((d) => (
              <button
                key={d.v}
                type="button"
                onClick={() => toggleDia(d.v)}
                disabled={isPending}
                className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
                  diasSemana.includes(d.v)
                    ? "border-brand-primary bg-brand-primary/20 text-brand-primary"
                    : "border-white/10 bg-obsidian-800 text-muted-foreground"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {/* Dias bloqueados */}
        <div>
          <label className="text-sm font-medium" htmlFor="db">
            Dias bloqueados (feriados/férias)
          </label>
          <input
            id="db"
            type="text"
            value={diasBloqueadosStr}
            onChange={(e) => setDiasBloqueadosStr(e.target.value)}
            placeholder="2026-12-25, 2026-12-31"
            className="mt-1.5 w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm font-mono"
            disabled={isPending}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Lista CSV no formato YYYY-MM-DD.
          </p>
        </div>

        {/* Requer aprovação */}
        <div className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={requerAprovacao}
              onChange={(e) => setRequerAprovacao(e.target.checked)}
              disabled={isPending}
              className="size-4"
            />
            <div>
              <span className="text-sm font-medium">
                Exigir aprovação do gestor
              </span>
              <p className="text-xs text-muted-foreground">
                Quando ativo, todo agendamento criado fica em status{" "}
                <code>pendente</code> até o gestor responder no WhatsApp
                com <code>APROVAR &lt;token&gt;</code> (telefone configurado em
                Integrações).
              </p>
            </div>
          </label>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {savedMsg && (
          <p className="text-sm text-emerald-400">{savedMsg}</p>
        )}

        <div className="flex justify-end pt-2">
          <Button onClick={handleSave} disabled={isPending}>
            <Save className="size-3.5" />
            Salvar regras
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
