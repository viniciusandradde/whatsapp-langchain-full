"use client";

import { useState, useTransition } from "react";
import { Plus, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  addAnotacaoAction,
  addTagAction,
  removeTagAction,
} from "../actions";

interface AnotacaoView {
  id: number;
  user_id: string;
  conteudo: string;
  created_at: string;
}

interface Props {
  clienteId: number;
  initialTags: string[];
  anotacoes: AnotacaoView[];
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR");
}

export function ClienteDetailClient({
  clienteId,
  initialTags,
  anotacoes,
}: Props) {
  const [tags, setTags] = useState<string[]>(initialTags);
  const [newTag, setNewTag] = useState("");
  const [newAnotacao, setNewAnotacao] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleAddTag() {
    const t = newTag.trim();
    if (!t) return;
    setError(null);
    startTransition(async () => {
      const r = await addTagAction(clienteId, t);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      if (!tags.includes(t)) setTags((prev) => [...prev, t].sort());
      setNewTag("");
    });
  }

  function handleRemoveTag(tag: string) {
    setError(null);
    startTransition(async () => {
      const r = await removeTagAction(clienteId, tag);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setTags((prev) => prev.filter((t) => t !== tag));
    });
  }

  function handleAddAnotacao() {
    const c = newAnotacao.trim();
    if (!c) return;
    setError(null);
    startTransition(async () => {
      const r = await addAnotacaoAction(clienteId, c);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      // revalidatePath traz a anotação nova no próximo render do server
      setNewAnotacao("");
    });
  }

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Tags
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1.5 pl-2 pr-1">
              {tag}
              <button
                type="button"
                onClick={() => handleRemoveTag(tag)}
                disabled={isPending}
                className="rounded p-0.5 hover:bg-foreground/10 disabled:opacity-50"
                aria-label={`Remover tag ${tag}`}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          {tags.length === 0 && (
            <span className="text-sm text-muted-foreground">
              Sem tags por enquanto.
            </span>
          )}
        </div>
        <div className="mt-3 flex max-w-sm gap-2">
          <input
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            placeholder="Nova tag"
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddTag();
              }
            }}
          />
          <Button
            size="sm"
            onClick={handleAddTag}
            disabled={isPending || !newTag.trim()}
          >
            <Plus className="size-3.5" />
            Adicionar
          </Button>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Anotações
        </h2>
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
            <textarea
              value={newAnotacao}
              onChange={(e) => setNewAnotacao(e.target.value)}
              placeholder="Adicionar nota sobre o cliente…"
              rows={3}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <Button
              onClick={handleAddAnotacao}
              disabled={isPending || !newAnotacao.trim()}
            >
              <Plus className="size-3.5" />
              Salvar nota
            </Button>
          </div>

          {anotacoes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Sem anotações ainda. Use o campo acima pra registrar contexto.
            </p>
          )}

          <ul className="space-y-2">
            {anotacoes.map((a) => (
              <li
                key={a.id}
                className="rounded-md border bg-card p-3 text-sm"
              >
                <p className="whitespace-pre-wrap">{a.conteudo}</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  {formatDateTime(a.created_at)} · {a.user_id}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
