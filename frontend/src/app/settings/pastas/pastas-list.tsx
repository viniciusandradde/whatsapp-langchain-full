"use client";

import { useMemo, useState, useTransition } from "react";
import { Folder, FolderTree, Pencil, Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Pasta } from "@/lib/api";

import { deletePastaAction, savePastaAction } from "./actions";

interface Props {
  initialPastas: Pasta[];
  loadError?: string | null;
}

type EditState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; pasta: Pasta };

interface TreeNode {
  pasta: Pasta;
  depth: number;
}

function flattenTree(pastas: Pasta[]): TreeNode[] {
  const byParent = new Map<number | null, Pasta[]>();
  for (const p of pastas) {
    const arr = byParent.get(p.parent_id) ?? [];
    arr.push(p);
    byParent.set(p.parent_id, arr);
  }
  for (const arr of byParent.values()) {
    arr.sort((a, b) => a.nome.localeCompare(b.nome));
  }
  const out: TreeNode[] = [];
  function walk(parentId: number | null, depth: number) {
    const children = byParent.get(parentId) ?? [];
    for (const p of children) {
      out.push({ pasta: p, depth });
      walk(p.id, depth + 1);
    }
  }
  walk(null, 0);
  return out;
}

export function PastasList({ initialPastas, loadError }: Props) {
  const [pastas, setPastas] = useState(initialPastas);
  const [edit, setEdit] = useState<EditState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const tree = useMemo(() => flattenTree(pastas), [pastas]);

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function parentOptions(currentId?: number) {
    return pastas.filter((p) => p.id !== currentId);
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await savePastaAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      const next = [...pastas];
      const idx = next.findIndex((p) => p.id === r.pasta.id);
      if (idx >= 0) next[idx] = r.pasta;
      else next.push(r.pasta);
      setPastas(next);
      setEdit({ mode: "closed" });
      setSuccess("Pasta salva.");
    });
  }

  function handleDelete(p: Pasta) {
    const docsLine =
      p.docs_count && p.docs_count > 0
        ? `\n${p.docs_count} documento(s) volta(m) pra raiz.`
        : "";
    if (!confirm(`Excluir a pasta "${p.nome}"?${docsLine}`)) return;
    clearMessages();
    startTransition(async () => {
      const r = await deletePastaAction(p.id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setPastas((prev) => prev.filter((x) => x.id !== p.id));
      setSuccess("Pasta removida.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Pastas da base de conhecimento</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {pastas.length === 0
                ? "Nenhuma pasta. Documentos ficam na raiz."
                : `${pastas.length} pasta(s) cadastrada(s).`}
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
            Nova pasta
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
              <input type="hidden" name="id" value={edit.pasta.id} />
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
                defaultValue={edit.mode === "edit" ? edit.pasta.nome : ""}
                placeholder="FAQ"
                required
                maxLength={120}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label
                htmlFor="parent_id"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Pasta pai (opcional)
              </label>
              <select
                id="parent_id"
                name="parent_id"
                defaultValue={
                  edit.mode === "edit"
                    ? String(edit.pasta.parent_id ?? "")
                    : ""
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">— Sem pai (raiz) —</option>
                {parentOptions(edit.mode === "edit" ? edit.pasta.id : undefined).map(
                  (p) => (
                    <option key={p.id} value={p.id}>
                      {p.nome}
                    </option>
                  )
                )}
              </select>
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
                  edit.mode === "edit" ? edit.pasta.descricao ?? "" : ""
                }
                maxLength={300}
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

        {pastas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Documentos atualmente ficam todos na raiz. Crie pastas pra
            organizar (ex: &quot;FAQ&quot;, &quot;Vendas/Promoções&quot;,
            &quot;Suporte&quot;).
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {tree.map(({ pasta: p, depth }) => (
              <li
                key={p.id}
                className="flex items-start justify-between gap-3 p-3"
                style={{ paddingLeft: `${0.75 + depth * 1.5}rem` }}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {depth > 0 && (
                      <span className="text-muted-foreground/50">↳</span>
                    )}
                    {depth === 0 ? (
                      <FolderTree className="size-4 text-brand-primary" />
                    ) : (
                      <Folder className="size-4 text-muted-foreground" />
                    )}
                    <p className="font-medium">{p.nome}</p>
                    {p.docs_count !== null && p.docs_count > 0 && (
                      <Badge variant="outline" className="text-[10px]">
                        {p.docs_count} doc{p.docs_count > 1 ? "s" : ""}
                      </Badge>
                    )}
                  </div>
                  {p.descricao && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {p.descricao}
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
                      setEdit({ mode: "edit", pasta: p });
                    }}
                    disabled={isPending}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(p)}
                    disabled={isPending}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <p className="rounded-md border border-dashed p-3 text-[11px] text-muted-foreground">
          Pra colocar documento numa pasta, hoje use o endpoint
          <code className="mx-1 rounded bg-white/[0.06] px-1 font-mono text-[10px]">
            POST /api/pastas/{`{id}`}/documentos/{`{doc_id}`}
          </code>
          ou inclua <code className="font-mono">pasta_id</code> no upload.
          Integração no UI do editor de agente vem em iteração seguinte.
        </p>
      </CardContent>
    </Card>
  );
}
