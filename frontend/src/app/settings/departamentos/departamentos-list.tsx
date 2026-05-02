"use client";

import { useState, useTransition } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Departamento } from "@/lib/api";

import {
  deleteDepartamentoAction,
  saveDepartamentoAction,
} from "./actions";

interface Props {
  initialDepartamentos: Departamento[];
  loadError?: string | null;
}

type EditState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; departamento: Departamento };

export function DepartamentosList({
  initialDepartamentos,
  loadError,
}: Props) {
  const [departamentos, setDepartamentos] = useState(initialDepartamentos);
  const [edit, setEdit] = useState<EditState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveDepartamentoAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      const next = [...departamentos];
      const idx = next.findIndex((d) => d.id === r.departamento.id);
      if (idx >= 0) next[idx] = r.departamento;
      else next.push(r.departamento);
      next.sort((a, b) => a.nome.localeCompare(b.nome));
      setDepartamentos(next);
      setEdit({ mode: "closed" });
      setSuccess("Departamento salvo.");
    });
  }

  function handleDelete(id: number, nome: string) {
    if (!confirm(`Excluir o departamento '${nome}'?`)) return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteDepartamentoAction(id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setDepartamentos((prev) => prev.filter((d) => d.id !== id));
      setSuccess("Departamento removido.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Departamentos cadastrados</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {departamentos.length === 0
                ? "Nenhum departamento ainda."
                : `${departamentos.length} cadastrado${departamentos.length > 1 ? "s" : ""}.`}
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              clearMessages();
              setEdit({ mode: "create" });
            }}
            disabled={isPending || edit.mode !== "closed"}
          >
            <Plus className="size-3.5" />
            Adicionar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadError && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {loadError}
          </p>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {success && <p className="text-sm text-emerald-300">{success}</p>}

        {edit.mode !== "closed" && (
          <form
            onSubmit={handleSubmit}
            className="space-y-3 rounded-md border bg-muted/20 p-4"
          >
            {edit.mode === "edit" && (
              <input
                type="hidden"
                name="id"
                value={edit.departamento.id}
              />
            )}
            <div>
              <label
                htmlFor="nome"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Nome
              </label>
              <input
                id="nome"
                name="nome"
                defaultValue={
                  edit.mode === "edit" ? edit.departamento.nome : ""
                }
                placeholder="Suporte"
                required
                maxLength={80}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label
                htmlFor="descricao"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Descrição (opcional)
              </label>
              <input
                id="descricao"
                name="descricao"
                defaultValue={
                  edit.mode === "edit"
                    ? edit.departamento.descricao ?? ""
                    : ""
                }
                maxLength={200}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="ativo"
                defaultChecked={
                  edit.mode === "edit" ? edit.departamento.ativo : true
                }
                className="size-4"
              />
              Ativo
            </label>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setEdit({ mode: "closed" })}
                disabled={isPending}
              >
                <X className="size-3.5" />
                Cancelar
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending ? "Salvando…" : "Salvar"}
              </Button>
            </div>
          </form>
        )}

        {departamentos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum departamento ainda. Adicione &quot;Suporte&quot;,
            &quot;Vendas&quot;, &quot;Financeiro&quot; pra começar.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {departamentos.map((d) => (
              <li
                key={d.id}
                className="flex items-start justify-between gap-3 p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{d.nome}</p>
                    {!d.ativo && (
                      <Badge variant="secondary">inativo</Badge>
                    )}
                  </div>
                  {d.descricao && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {d.descricao}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      clearMessages();
                      setEdit({ mode: "edit", departamento: d });
                    }}
                    disabled={isPending}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(d.id, d.nome)}
                    disabled={isPending}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
