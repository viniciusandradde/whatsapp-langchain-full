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
import type { VariavelAmbiente } from "@/lib/api";

import { deleteVariavelAction, saveVariavelAction } from "./actions";

interface Props {
  initialVariaveis: VariavelAmbiente[];
  loadError?: string | null;
}

type EditState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; variavel: VariavelAmbiente };

export function VariaveisList({ initialVariaveis, loadError }: Props) {
  const [variaveis, setVariaveis] = useState(initialVariaveis);
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
      const r = await saveVariavelAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      const next = [...variaveis];
      const idx = next.findIndex((v) => v.id === r.variavel.id);
      if (idx >= 0) next[idx] = r.variavel;
      else next.push(r.variavel);
      next.sort((a, b) => a.nome.localeCompare(b.nome));
      setVariaveis(next);
      setEdit({ mode: "closed" });
      setSuccess("Variável salva.");
    });
  }

  function handleDelete(id: number, nome: string) {
    if (!confirm(`Excluir a variável \`${nome}\`?`)) return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteVariavelAction(id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setVariaveis((prev) => prev.filter((v) => v.id !== id));
      setSuccess("Variável removida.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Variáveis cadastradas</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {variaveis.length === 0
                ? "Nenhuma variável ainda."
                : `${variaveis.length} cadastrada${variaveis.length > 1 ? "s" : ""}.`}
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
              <input type="hidden" name="id" value={edit.variavel.id} />
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="nome"
                  className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
                >
                  Nome (chave)
                </label>
                <input
                  id="nome"
                  name="nome"
                  defaultValue={
                    edit.mode === "edit" ? edit.variavel.nome : ""
                  }
                  placeholder="suporte_email"
                  required
                  pattern="^[a-zA-Z][a-zA-Z0-9_]*$"
                  maxLength={64}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Letras, números e _. Referência:{" "}
                  <code className="rounded bg-muted px-1 py-0.5">
                    {"{{var.NOME}}"}
                  </code>
                </p>
              </div>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input
                  type="checkbox"
                  name="ativo"
                  defaultChecked={
                    edit.mode === "edit" ? edit.variavel.ativo : true
                  }
                  className="size-4"
                />
                Ativo (resolver no render)
              </label>
            </div>
            <div>
              <label
                htmlFor="valor"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Valor
              </label>
              <textarea
                id="valor"
                name="valor"
                defaultValue={
                  edit.mode === "edit" ? edit.variavel.valor : ""
                }
                rows={3}
                maxLength={4000}
                placeholder="Texto que substitui a chave no render."
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
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
                  edit.mode === "edit" ? edit.variavel.descricao ?? "" : ""
                }
                maxLength={200}
                placeholder="Pra onde os clientes mandam dúvida de produto"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
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

        {variaveis.length === 0 ? (
          <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
            <p>
              Nenhuma variável ainda. Variáveis comuns:{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                suporte_email
              </code>
              ,{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                horario_atendimento
              </code>
              ,{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                link_catalogo
              </code>
              .
            </p>
            <p className="mt-2">
              Namespaces fixos disponíveis sem cadastro:{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                empresa.nome
              </code>
              ,{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                cliente.nome
              </code>
              ,{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                data.hoje
              </code>
              .
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border">
            {variaveis.map((v) => (
              <li
                key={v.id}
                className="flex items-start justify-between gap-3 p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      {`{{var.${v.nome}}}`}
                    </code>
                    {!v.ativo && <Badge variant="secondary">inativo</Badge>}
                  </div>
                  <p className="mt-1 line-clamp-2 break-words text-sm">
                    {v.valor || (
                      <span className="italic text-muted-foreground">
                        (vazio)
                      </span>
                    )}
                  </p>
                  {v.descricao && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {v.descricao}
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
                      setEdit({ mode: "edit", variavel: v });
                    }}
                    disabled={isPending}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(v.id, v.nome)}
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
