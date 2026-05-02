"use client";

import { useState, useTransition } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  BuscarDocumentosResponse,
  DocumentoConhecimento,
} from "@/lib/api";

import {
  buscarDocumentosAction,
  deleteDocumentoAction,
  saveDocumentoAction,
} from "./actions";

interface Props {
  agentId: string;
  initialDocumentos: DocumentoConhecimento[];
  loadError?: string | null;
}

type EditState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; doc: DocumentoConhecimento };

export function BaseConhecimentoList({
  agentId,
  initialDocumentos,
  loadError,
}: Props) {
  const [docs, setDocs] = useState(initialDocumentos);
  const [edit, setEdit] = useState<EditState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [isPending, startTransition] = useTransition();
  const [busca, setBusca] = useState("");
  const [resultados, setResultados] = useState<
    BuscarDocumentosResponse["resultados"] | null
  >(null);

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function toggleExpand(id: number) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setExpanded(next);
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveDocumentoAction(agentId, form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      const next = [...docs];
      const idx = next.findIndex((d) => d.id === r.documento.id);
      if (idx >= 0) next[idx] = r.documento;
      else next.unshift(r.documento);
      setDocs(next);
      setEdit({ mode: "closed" });
      setSuccess("Documento salvo.");
    });
  }

  function handleDelete(id: number) {
    if (!confirm("Excluir este documento? Essa ação não pode ser desfeita."))
      return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteDocumentoAction(agentId, id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setDocs((prev) => prev.filter((d) => d.id !== id));
      setSuccess("Documento removido.");
    });
  }

  function handleBuscar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    if (!busca.trim()) {
      setResultados(null);
      return;
    }
    startTransition(async () => {
      const r = await buscarDocumentosAction(busca.trim());
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setResultados(r.data.resultados);
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <BookOpen className="size-4 text-muted-foreground" />
            <div>
              <CardTitle>Base de Conhecimento</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Documentos que o agente consulta antes de responder.
                {docs.length > 0 && ` ${docs.length} cadastrado${docs.length > 1 ? "s" : ""}.`}
              </p>
            </div>
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
              <input type="hidden" name="id" value={edit.doc.id} />
            )}
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
                defaultValue={edit.mode === "edit" ? edit.doc.titulo : ""}
                placeholder="Ex: Política de trocas"
                required
                maxLength={200}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
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
                defaultValue={edit.mode === "edit" ? edit.doc.conteudo : ""}
                rows={8}
                maxLength={20000}
                required
                placeholder="Texto completo da política/FAQ. O agente vai citar esse conteúdo na resposta."
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="tags"
                  className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
                >
                  Tags{" "}
                  <span className="normal-case">(separadas por vírgula)</span>
                </label>
                <input
                  id="tags"
                  name="tags"
                  defaultValue={
                    edit.mode === "edit" ? edit.doc.tags.join(", ") : ""
                  }
                  placeholder="trocas, políticas"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input
                  type="checkbox"
                  name="ativo"
                  defaultChecked={
                    edit.mode === "edit" ? edit.doc.ativo : true
                  }
                  className="size-4"
                />
                Documento ativo
              </label>
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

        {docs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum documento cadastrado. Adicione FAQs, políticas ou
            scripts pra que o agente cite esse conteúdo nas respostas.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {docs.map((doc) => {
              const isOpen = expanded.has(doc.id);
              return (
                <li key={doc.id} className="p-3">
                  <div className="flex items-start justify-between gap-3">
                    <button
                      type="button"
                      onClick={() => toggleExpand(doc.id)}
                      className="flex flex-1 items-start gap-2 text-left"
                    >
                      {isOpen ? (
                        <ChevronDown className="mt-0.5 size-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="mt-0.5 size-4 text-muted-foreground" />
                      )}
                      <div className="min-w-0">
                        <p className="font-medium">{doc.titulo}</p>
                        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                          {doc.conteudo}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-1">
                          {!doc.ativo && (
                            <Badge variant="secondary">inativo</Badge>
                          )}
                          {doc.tags.map((tag) => (
                            <Badge key={tag} variant="outline">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </button>
                    <div className="flex shrink-0 gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          clearMessages();
                          setEdit({ mode: "edit", doc });
                        }}
                        disabled={isPending}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDelete(doc.id)}
                        disabled={isPending}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                  {isOpen && (
                    <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                      {doc.conteudo}
                    </pre>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <div className="border-t pt-4">
          <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
            Testar busca
          </p>
          <form onSubmit={handleBuscar} className="flex gap-2">
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Pergunta de teste (ex: posso trocar produto?)"
              className="flex h-10 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <Button type="submit" disabled={isPending || !busca.trim()}>
              <Search className="size-3.5" />
              Buscar
            </Button>
          </form>
          {resultados !== null && (
            <div className="mt-3 space-y-2">
              {resultados.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nenhum documento relevante para essa pergunta.
                </p>
              ) : (
                resultados.map((r) => (
                  <div
                    key={r.documento.id}
                    className="rounded-md border bg-muted/20 p-3 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {r.documento.titulo}
                      </span>
                      <Badge variant="outline">
                        relevância {r.score.toFixed(2)}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                      {r.documento.conteudo}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
