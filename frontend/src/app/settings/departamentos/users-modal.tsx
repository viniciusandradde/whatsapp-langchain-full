"use client";

import { useEffect, useState, useTransition } from "react";
import { Plus, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Departamento, DepartamentoUser } from "@/lib/api";

import {
  assignUserAction,
  listDepartamentoUsersAction,
  unassignUserAction,
} from "./actions";

interface Props {
  departamento: Departamento;
  onClose: () => void;
}

/**
 * Modal de membros do departamento (E2.B).
 *
 * Mostra lista de users atribuídos + input pra adicionar por user_id
 * (auth.user.id, UUID). MVP — pra UX melhor seria ter um picker de
 * email/nome buscando em /api/empresas/{id}/members, fica como follow-up.
 */
export function UsersModal({ departamento, onClose }: Props) {
  const [users, setUsers] = useState<DepartamentoUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newUserId, setNewUserId] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const r = await listDepartamentoUsersAction(departamento.id);
      if (cancelled) return;
      if (r.ok) setUsers(r.items);
      else setError(r.error);
    })();
    return () => {
      cancelled = true;
    };
  }, [departamento.id]);

  function refresh() {
    startTransition(async () => {
      const r = await listDepartamentoUsersAction(departamento.id);
      if (r.ok) setUsers(r.items);
      else setError(r.error);
    });
  }

  function handleAdd() {
    if (!newUserId.trim()) return;
    setError(null);
    startTransition(async () => {
      const r = await assignUserAction(departamento.id, newUserId);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setNewUserId("");
      refresh();
    });
  }

  function handleRemove(userId: string) {
    if (!confirm("Remover esse user do departamento?")) return;
    setError(null);
    startTransition(async () => {
      const r = await unassignUserAction(departamento.id, userId);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      refresh();
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-lg bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">
            Membros — {departamento.nome}
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar">
            <X className="size-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Adicionar membro (user_id UUID)
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                placeholder="9d096dc9-dd81-4f72-..."
                disabled={isPending}
                className="flex h-10 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono text-xs"
              />
              <Button onClick={handleAdd} disabled={isPending || !newUserId.trim()}>
                <Plus className="size-3.5" />
                Add
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Pegue o user_id em /companies/{departamento.empresa_id}/members.
            </p>
          </div>

          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Membros atuais ({users?.length ?? "…"})
            </p>
            {users === null ? (
              <p className="text-sm text-muted-foreground">Carregando…</p>
            ) : users.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhum membro ainda. Sem membros, atendimentos com esse
                departamento não aparecem pra ninguém com scope ativo.
              </p>
            ) : (
              <ul className="divide-y rounded-md border">
                {users.map((u) => (
                  <li
                    key={u.user_id}
                    className="flex items-center justify-between gap-2 p-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">
                        {u.name || u.email || u.user_id.slice(0, 8)}
                      </p>
                      {u.email && u.name && (
                        <p className="text-xs text-muted-foreground">{u.email}</p>
                      )}
                      <p className="font-mono text-[10px] text-muted-foreground/70">
                        {u.user_id}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleRemove(u.user_id)}
                      disabled={isPending}
                      title="Remover"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <footer className="flex justify-end border-t p-4">
          <Button variant="ghost" onClick={onClose}>
            Fechar
          </Button>
        </footer>
      </div>
    </div>
  );
}
