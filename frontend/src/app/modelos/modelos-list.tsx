"use client";

import { useState, useTransition } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ModeloMensagem } from "@/lib/api";

import { deleteModeloAction, saveModelo } from "./actions";

interface Props {
  modelos: ModeloMensagem[];
}

type Editing = ModeloMensagem | "new" | null;

export function ModelosList({ modelos }: Props) {
  const [editing, setEditing] = useState<Editing>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleDelete(id: number) {
    if (
      !confirm("Excluir este modelo? Os atendimentos não são afetados.")
    )
      return;
    setError(null);
    startTransition(async () => {
      const r = await deleteModeloAction(id);
      if (!r.ok) setError(r.error);
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Modelos são respostas reutilizáveis que aparecem como atalho no
          composer do atendimento. Cada empresa tem sua própria coleção.
        </p>
        {editing !== "new" && (
          <Button onClick={() => setEditing("new")} variant="default">
            <Plus className="size-4" />
            Novo modelo
          </Button>
        )}
      </div>

      {editing === "new" && (
        <ModeloForm onDone={() => setEditing(null)} />
      )}
      {editing && editing !== "new" && (
        <ModeloForm initial={editing} onDone={() => setEditing(null)} />
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {modelos.length === 0 && !editing && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhum modelo cadastrado</p>
          <p className="mt-1 text-sm">
            Crie textos curtos reutilizáveis pra inserir no atendimento com 2
            cliques.
          </p>
        </div>
      )}

      {modelos.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {modelos.map((m) => (
            <Card key={m.id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">{m.titulo}</CardTitle>
                    {m.atalho && (
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        {m.atalho}
                      </p>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="text-sm">
                <p className="whitespace-pre-wrap text-muted-foreground">
                  {m.conteudo.length > 220
                    ? m.conteudo.slice(0, 220) + "…"
                    : m.conteudo}
                </p>
              </CardContent>
              <div className="flex items-center justify-end gap-2 px-4 pb-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditing(m)}
                  disabled={isPending}
                >
                  <Pencil className="size-3.5" />
                  Editar
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(m.id)}
                  disabled={isPending}
                >
                  <Trash2 className="size-3.5" />
                  Excluir
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function ModeloForm({
  initial,
  onDone,
}: {
  initial?: ModeloMensagem;
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveModelo(initial?.id ?? null, form);
      if (!r.ok) setError(r.error);
      else onDone();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{initial ? "Editar modelo" : "Novo modelo"}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="titulo"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              Título
            </label>
            <input
              id="titulo"
              name="titulo"
              defaultValue={initial?.titulo ?? ""}
              required
              maxLength={120}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label
              htmlFor="atalho"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              Atalho <span className="normal-case">(opcional)</span>
            </label>
            <input
              id="atalho"
              name="atalho"
              defaultValue={initial?.atalho ?? ""}
              maxLength={64}
              placeholder="ex: /saudacao"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label
              htmlFor="conteudo"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              Conteúdo
            </label>
            <textarea
              id="conteudo"
              name="conteudo"
              defaultValue={initial?.conteudo ?? ""}
              required
              rows={5}
              maxLength={4000}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
