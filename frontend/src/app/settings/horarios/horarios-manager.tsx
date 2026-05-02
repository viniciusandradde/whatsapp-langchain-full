"use client";

import { useState, useTransition } from "react";
import { CalendarDays, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Feriado, HorarioFuncionamento } from "@/lib/api";

import {
  deleteFeriadoAction,
  deleteHorarioAction,
  saveFeriadoAction,
  saveHorarioAction,
} from "./actions";

interface Props {
  initialHorarios: HorarioFuncionamento[];
  initialFeriados: Feriado[];
  loadError?: string | null;
}

const DIAS = [
  "Domingo",
  "Segunda",
  "Terça",
  "Quarta",
  "Quinta",
  "Sexta",
  "Sábado",
];

export function HorariosManager({
  initialHorarios,
  initialFeriados,
  loadError,
}: Props) {
  const [horarios, setHorarios] = useState(initialHorarios);
  const [feriados, setFeriados] = useState(initialFeriados);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [diaForm, setDiaForm] = useState<number | null>(null);
  const [feriadoOpen, setFeriadoOpen] = useState(false);
  const [isPending, startTransition] = useTransition();

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function horariosOf(dia: number) {
    return horarios
      .filter((h) => h.dia_semana === dia && h.departamento_id === null)
      .sort((a, b) => a.hora_inicio.localeCompare(b.hora_inicio));
  }

  function handleSubmitHorario(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveHorarioAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setHorarios((prev) => [...prev, r.horario]);
      setDiaForm(null);
      setSuccess("Janela adicionada.");
    });
  }

  function handleDeleteHorario(id: number) {
    if (!confirm("Remover essa janela de horário?")) return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteHorarioAction(id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setHorarios((prev) => prev.filter((h) => h.id !== id));
      setSuccess("Janela removida.");
    });
  }

  function handleSubmitFeriado(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveFeriadoAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setFeriados((prev) =>
        [...prev, r.feriado].sort((a, b) => a.data.localeCompare(b.data))
      );
      setFeriadoOpen(false);
      setSuccess("Feriado adicionado.");
    });
  }

  function handleDeleteFeriado(id: number) {
    if (!confirm("Remover esse feriado?")) return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteFeriadoAction(id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setFeriados((prev) => prev.filter((f) => f.id !== id));
      setSuccess("Feriado removido.");
    });
  }

  return (
    <div className="space-y-6">
      {loadError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-300">{success}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Janelas por dia da semana</CardTitle>
          <p className="text-xs text-muted-foreground">
            Adicione múltiplas janelas no mesmo dia pra cobrir intervalo
            de almoço (ex: 09:00-12:00 e 13:00-18:00). Sem janela
            cadastrada = empresa fechada nesse dia.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {DIAS.map((nome, idx) => {
            const items = horariosOf(idx);
            const formOpen = diaForm === idx;
            return (
              <div
                key={idx}
                className="rounded-md border bg-muted/10 p-3"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">{nome}</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      clearMessages();
                      setDiaForm(formOpen ? null : idx);
                    }}
                    disabled={isPending}
                  >
                    <Plus className="size-3.5" />
                    Adicionar janela
                  </Button>
                </div>
                {items.length === 0 && !formOpen && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Sem expediente nesse dia.
                  </p>
                )}
                {items.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {items.map((h) => (
                      <li
                        key={h.id}
                        className="inline-flex items-center gap-2 rounded-md border bg-background px-2 py-1 font-mono text-xs"
                      >
                        {h.hora_inicio} – {h.hora_fim}
                        <button
                          type="button"
                          onClick={() => handleDeleteHorario(h.id)}
                          disabled={isPending}
                          className="opacity-60 hover:opacity-100"
                          aria-label="remover"
                        >
                          <Trash2 className="size-3" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {formOpen && (
                  <form
                    onSubmit={handleSubmitHorario}
                    className="mt-2 flex flex-wrap items-end gap-2"
                  >
                    <input type="hidden" name="dia_semana" value={idx} />
                    <div>
                      <label className="block text-xs uppercase tracking-wide text-muted-foreground">
                        Início
                      </label>
                      <input
                        type="time"
                        name="hora_inicio"
                        required
                        defaultValue="09:00"
                        className="flex h-10 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      />
                    </div>
                    <div>
                      <label className="block text-xs uppercase tracking-wide text-muted-foreground">
                        Fim
                      </label>
                      <input
                        type="time"
                        name="hora_fim"
                        required
                        defaultValue="18:00"
                        className="flex h-10 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      />
                    </div>
                    <Button type="submit" size="sm" disabled={isPending}>
                      {isPending ? "Salvando…" : "Salvar"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setDiaForm(null)}
                    >
                      Cancelar
                    </Button>
                  </form>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <CalendarDays className="size-4 text-muted-foreground" />
              <div>
                <CardTitle>Feriados</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Datas em que estamos fechados o dia inteiro,
                  independentemente do horário cadastrado.
                </p>
              </div>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                clearMessages();
                setFeriadoOpen(true);
              }}
              disabled={isPending || feriadoOpen}
            >
              <Plus className="size-3.5" />
              Adicionar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {feriadoOpen && (
            <form
              onSubmit={handleSubmitFeriado}
              className="flex flex-wrap items-end gap-2 rounded-md border bg-muted/20 p-3"
            >
              <div>
                <label className="block text-xs uppercase tracking-wide text-muted-foreground">
                  Data
                </label>
                <input
                  type="date"
                  name="data"
                  required
                  className="flex h-10 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs uppercase tracking-wide text-muted-foreground">
                  Descrição
                </label>
                <input
                  name="descricao"
                  placeholder="Natal"
                  maxLength={200}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <Button type="submit" size="sm" disabled={isPending}>
                {isPending ? "Salvando…" : "Salvar"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setFeriadoOpen(false)}
              >
                Cancelar
              </Button>
            </form>
          )}

          {feriados.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum feriado cadastrado.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {feriados.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center justify-between gap-3 p-3"
                >
                  <div>
                    <p className="font-mono text-sm">{f.data}</p>
                    {f.descricao && (
                      <p className="text-xs text-muted-foreground">
                        {f.descricao}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDeleteFeriado(f.id)}
                    disabled={isPending}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
