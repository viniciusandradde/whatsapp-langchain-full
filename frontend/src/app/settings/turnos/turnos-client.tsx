"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { Clock, Loader2, Pencil, Plus, Trash2, Users, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/components/ui/api-error";
import { EmptyState } from "@/components/ui/empty-state";
import type { Turno } from "@/lib/api";

import {
  atualizarTurnoAction,
  criarTurnoAction,
  deletarTurnoAction,
  loadTurnoUsersAction,
  loadTurnosAction,
  setTurnoUsersAction,
} from "./actions";

const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

interface DiaRow {
  enabled: boolean;
  inicio: string;
  fim: string;
}

export function TurnosClient() {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState<Turno | null>(null);
  const [creating, setCreating] = useState(false);
  const [managingUsers, setManagingUsers] = useState<Turno | null>(null);
  const [pending, startTransition] = useTransition();

  const reload = useCallback(() => {
    let alive = true;
    loadTurnosAction()
      .then((r) => {
        if (!alive) return;
        if (r.ok) {
          setTurnos(r.data);
          setError(null);
        } else {
          setError(new Error(r.error));
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => reload(), [reload]);

  function handleDelete(t: Turno) {
    if (!confirm(`Remover o turno "${t.nome}"?`)) return;
    startTransition(async () => {
      const r = await deletarTurnoAction(t.id);
      if (r.ok) reload();
      else alert("Erro: " + r.error);
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreating(true)}>
          <Plus className="mr-1 size-4" />
          Novo turno
        </Button>
      </div>

      {error ? (
        <ApiError error={error} variant="card" />
      ) : loading ? (
        <div className="flex items-center gap-2 p-8 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Carregando turnos…
        </div>
      ) : turnos.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="Nenhum turno cadastrado"
          description="Crie turnos pra organizar a jornada dos atendentes."
          action={{ label: "Novo turno", onClick: () => setCreating(true) }}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {turnos.map((t) => (
            <div
              key={t.id}
              className="rounded-xl border border-white/10 bg-obsidian-900 p-4"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="flex items-center gap-2 font-medium">
                    {t.nome}
                    {!t.ativo && (
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        inativo
                      </span>
                    )}
                  </h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {t.users_count} atendente(s)
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" title="Atendentes" onClick={() => setManagingUsers(t)}>
                    <Users className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" title="Editar" onClick={() => setEditing(t)}>
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" title="Remover" disabled={pending} onClick={() => handleDelete(t)}>
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {t.horarios.length === 0 ? (
                  <span className="text-xs italic text-muted-foreground">Sem horários</span>
                ) : (
                  t.horarios.map((h, i) => (
                    <span
                      key={i}
                      className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px]"
                    >
                      {DIAS[h.dia_semana]} {h.hora_inicio}–{h.hora_fim}
                    </span>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {(creating || editing) && (
        <TurnoFormModal
          turno={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            reload();
          }}
        />
      )}
      {managingUsers && (
        <TurnoUsersModal
          turno={managingUsers}
          onClose={() => setManagingUsers(null)}
          onSaved={() => {
            setManagingUsers(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function TurnoFormModal({
  turno,
  onClose,
  onSaved,
}: {
  turno: Turno | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = turno !== null;
  const [nome, setNome] = useState(turno?.nome ?? "");
  const [ativo, setAtivo] = useState(turno?.ativo ?? true);
  const [dias, setDias] = useState<DiaRow[]>(() =>
    DIAS.map((_, i) => {
      const h = turno?.horarios.find((x) => x.dia_semana === i);
      return {
        enabled: !!h,
        inicio: h?.hora_inicio ?? "08:00",
        fim: h?.hora_fim ?? "18:00",
      };
    })
  );
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function setDia(i: number, patch: Partial<DiaRow>) {
    setDias((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }

  function save() {
    setError(null);
    if (!nome.trim()) {
      setError("Informe o nome do turno.");
      return;
    }
    const horarios = dias
      .map((d, i) => ({ ...d, dia_semana: i }))
      .filter((d) => d.enabled)
      .map((d) => ({ dia_semana: d.dia_semana, hora_inicio: d.inicio, hora_fim: d.fim }));
    for (const h of horarios) {
      if (h.hora_fim <= h.hora_inicio) {
        setError(`${DIAS[h.dia_semana]}: fim deve ser maior que início.`);
        return;
      }
    }
    start(async () => {
      const body = { nome: nome.trim(), ativo, horarios };
      const r =
        isEdit && turno
          ? await atualizarTurnoAction(turno.id, body)
          : await criarTurnoAction(body);
      if (r.ok) onSaved();
      else setError(r.error);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-obsidian-900 shadow-vsa-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 className="text-sm font-semibold">{isEdit ? "Editar turno" : "Novo turno"}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>
        <div className="space-y-3 px-4 py-4 text-sm">
          <div className="flex items-center gap-3">
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Nome do turno (ex: Comercial)"
              className="flex-1 rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5"
              autoFocus
            />
            <label className="flex items-center gap-1.5 text-xs">
              <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
              Ativo
            </label>
          </div>

          <div className="space-y-1.5">
            {dias.map((d, i) => (
              <div key={i} className="flex items-center gap-2">
                <label className="flex w-16 items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={d.enabled}
                    onChange={(e) => setDia(i, { enabled: e.target.checked })}
                  />
                  {DIAS[i]}
                </label>
                <input
                  type="time"
                  value={d.inicio}
                  disabled={!d.enabled}
                  onChange={(e) => setDia(i, { inicio: e.target.value })}
                  className="rounded-md border border-white/10 bg-obsidian-800 px-2 py-1 disabled:opacity-40"
                />
                <span className="text-muted-foreground">até</span>
                <input
                  type="time"
                  value={d.fim}
                  disabled={!d.enabled}
                  onChange={(e) => setDia(i, { fim: e.target.value })}
                  className="rounded-md border border-white/10 bg-obsidian-800 px-2 py-1 disabled:opacity-40"
                />
              </div>
            ))}
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-white/10 px-4 py-3">
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={save} disabled={pending}>
            {pending && <Loader2 className="mr-1 size-4 animate-spin" />}
            {isEdit ? "Salvar" : "Criar"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function TurnoUsersModal({
  turno,
  onClose,
  onSaved,
}: {
  turno: Turno;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [all, setAll] = useState<{ id: string; nome: string | null }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  useEffect(() => {
    let alive = true;
    loadTurnoUsersAction(turno.id)
      .then((r) => {
        if (!alive) return;
        if (r.ok) {
          setAll(r.data.all);
          setSelected(new Set(r.data.assigned));
        } else {
          setError(r.error);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [turno.id]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function save() {
    start(async () => {
      const r = await setTurnoUsersAction(turno.id, [...selected]);
      if (r.ok) onSaved();
      else setError(r.error);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-obsidian-900 shadow-vsa-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 className="text-sm font-semibold">Atendentes — {turno.nome}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>
        <div className="max-h-80 overflow-y-auto px-4 py-3 text-sm">
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Carregando…
            </div>
          ) : all.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">Nenhum usuário ativo.</p>
          ) : (
            <div className="space-y-1">
              {all.map((u) => (
                <label
                  key={u.id}
                  className="flex items-center gap-2 rounded p-1.5 hover:bg-white/[0.04]"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(u.id)}
                    onChange={() => toggle(u.id)}
                  />
                  <span>{u.nome || u.id}</span>
                </label>
              ))}
            </div>
          )}
          {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-white/10 px-4 py-3">
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={save} disabled={pending || loading}>
            {pending && <Loader2 className="mr-1 size-4 animate-spin" />}
            Salvar
          </Button>
        </div>
      </div>
    </div>
  );
}
