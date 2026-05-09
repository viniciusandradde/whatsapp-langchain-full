"use client";

import { useMemo, useState, useTransition } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderTree,
  Loader2,
  MoveRight,
  Pencil,
  Plus,
  Trash2,
  Upload,
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
import type { DocumentoConhecimento, Pasta } from "@/lib/api";

import {
  deleteDocumentoAction,
  deletePastaAction,
  moveDocumentoAction,
  saveDocumentoAction,
  savePastaAction,
  triggerLearnerAction,
  uploadFileToFolderAction,
} from "./actions";

interface Props {
  initialPastas: Pasta[];
  initialDocumentos: DocumentoConhecimento[];
  loadError?: string | null;
}

type PastaEditState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; pasta: Pasta };

type DocEditState =
  | { mode: "closed" }
  | { mode: "create"; pastaId: number | null }
  | { mode: "edit"; doc: DocumentoConhecimento };

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

export function PastasList({
  initialPastas,
  initialDocumentos,
  loadError,
}: Props) {
  const [pastas, setPastas] = useState(initialPastas);
  const [documentos, setDocumentos] = useState(initialDocumentos);
  const [pastaEdit, setPastaEdit] = useState<PastaEditState>({ mode: "closed" });
  const [docEdit, setDocEdit] = useState<DocEditState>({ mode: "closed" });
  const [expanded, setExpanded] = useState<Set<number | null>>(
    () => new Set([null]) // raiz expandida por default
  );
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [uploadPastaId, setUploadPastaId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const tree = useMemo(() => flattenTree(pastas), [pastas]);

  const docsByPasta = useMemo(() => {
    const m = new Map<number | null, DocumentoConhecimento[]>();
    for (const d of documentos) {
      const arr = m.get(d.pasta_id) ?? [];
      arr.push(d);
      m.set(d.pasta_id, arr);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => a.titulo.localeCompare(b.titulo));
    }
    return m;
  }, [documentos]);

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function toggleExpand(id: number | null) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function parentOptions(currentId?: number) {
    return pastas.filter((p) => p.id !== currentId);
  }

  function handleSubmitPasta(e: React.FormEvent<HTMLFormElement>) {
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
      setPastaEdit({ mode: "closed" });
      setSuccess("Pasta salva.");
    });
  }

  function handleDeletePasta(p: Pasta) {
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
      setDocumentos((prev) =>
        prev.map((d) => (d.pasta_id === p.id ? { ...d, pasta_id: null } : d))
      );
      setSuccess("Pasta removida.");
    });
  }

  function handleSubmitDoc(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clearMessages();
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveDocumentoAction(form);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      const next = [...documentos];
      const idx = next.findIndex((d) => d.id === r.doc.id);
      if (idx >= 0) next[idx] = r.doc;
      else next.push(r.doc);
      setDocumentos(next);
      // Atualiza docs_count da pasta destino
      setPastas((prev) =>
        prev.map((p) => {
          let count = next.filter((d) => d.pasta_id === p.id).length;
          return { ...p, docs_count: count };
        })
      );
      setDocEdit({ mode: "closed" });
      setSuccess("Documento salvo.");
    });
  }

  function handleDeleteDoc(d: DocumentoConhecimento) {
    if (!confirm(`Excluir o documento "${d.titulo}"?`)) return;
    clearMessages();
    startTransition(async () => {
      const r = await deleteDocumentoAction(d.id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setDocumentos((prev) => prev.filter((x) => x.id !== d.id));
      setPastas((prev) =>
        prev.map((p) =>
          p.id === d.pasta_id
            ? { ...p, docs_count: Math.max(0, (p.docs_count ?? 0) - 1) }
            : p
        )
      );
      setSuccess("Documento removido.");
    });
  }

  async function handleAnalyzeSandbox() {
    clearMessages();
    setAnalyzing(true);
    const r = await triggerLearnerAction();
    setAnalyzing(false);
    if (!r.ok) {
      setError(`Falha analyze: ${r.error}`);
      return;
    }
    setSuccess(
      `🧪 Analisado: ${r.misses} misses → ${r.clusters} clusters → ${r.suggestions_created} sugestões. Veja em /dashboard/rag/sandbox`
    );
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    clearMessages();
    setUploading(true);
    let totalDocs = 0;
    let totalFiles = 0;
    const errors: string[] = [];
    for (const f of files) {
      const fd = new FormData();
      fd.set("arquivo", f, f.name);
      const r = await uploadFileToFolderAction(uploadPastaId, fd);
      if (r.ok) {
        totalDocs += r.docs_created;
        totalFiles += 1;
      } else {
        errors.push(`${r.filename}: ${r.error}`);
      }
    }
    setUploading(false);
    e.target.value = "";  // reset input
    if (errors.length === 0) {
      setSuccess(
        `${totalFiles} arquivo(s) → ${totalDocs} doc(s) criado(s)` +
          (uploadPastaId ? ` na pasta selecionada` : ` na raiz`)
      );
    } else {
      setError(`${totalDocs} OK / ${errors.length} falhas:\n${errors.slice(0, 3).join("\n")}`);
    }
  }

  function handleMoveDoc(d: DocumentoConhecimento, newPastaId: number | null) {
    if (newPastaId === d.pasta_id) return;
    clearMessages();
    startTransition(async () => {
      const r = await moveDocumentoAction(d.id, newPastaId);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setDocumentos((prev) =>
        prev.map((x) => (x.id === d.id ? { ...x, pasta_id: newPastaId } : x))
      );
      // Recalcula docs_count
      setPastas((prev) =>
        prev.map((p) => {
          const count = documentos
            .map((x) => (x.id === d.id ? { ...x, pasta_id: newPastaId } : x))
            .filter((x) => x.pasta_id === p.id).length;
          return { ...p, docs_count: count };
        })
      );
      setSuccess("Documento movido.");
    });
  }

  const renderDocItem = (d: DocumentoConhecimento, indent: number) => (
    <div
      key={d.id}
      className="flex items-start justify-between gap-2 border-b py-2 pr-2 last:border-0"
      style={{ paddingLeft: `${indent}rem` }}
    >
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{d.titulo}</p>
          <p className="line-clamp-1 text-[11px] text-muted-foreground">
            {d.conteudo.slice(0, 120)}
            {d.conteudo.length > 120 ? "…" : ""}
          </p>
        </div>
        {!d.ativo && (
          <Badge variant="secondary" className="text-[9px]">
            Inativo
          </Badge>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <select
          aria-label="Mover documento"
          value={String(d.pasta_id ?? "")}
          onChange={(e) =>
            handleMoveDoc(
              d,
              e.target.value === "" ? null : Number(e.target.value)
            )
          }
          disabled={isPending}
          className="h-7 rounded-md border border-input bg-background px-1 text-xs"
        >
          <option value="">— Raiz —</option>
          {pastas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            clearMessages();
            setDocEdit({ mode: "edit", doc: d });
          }}
          disabled={isPending}
        >
          <Pencil className="size-3.5" />
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => handleDeleteDoc(d)}
          disabled={isPending}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Pastas + Documentos</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {pastas.length} pasta(s) — {documentos.length} doc(s) total
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                clearMessages();
                setDocEdit({ mode: "create", pastaId: null });
              }}
              disabled={isPending || docEdit.mode !== "closed"}
            >
              <FileText className="size-3.5" />
              Novo doc
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                clearMessages();
                setPastaEdit({ mode: "create" });
              }}
              disabled={isPending || pastaEdit.mode !== "closed"}
            >
              <Plus className="size-3.5" />
              Nova pasta
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadError && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {loadError}
          </p>
        )}

        {/* Sprint S.2 — Upload arquivo (.md splita por H1/H2 automático) */}
        <div className="rounded-md border border-emerald-500/30 bg-emerald-950/10 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Upload className="size-4 text-emerald-400" />
            <span className="text-sm font-medium">Upload arquivo</span>
            <select
              value={String(uploadPastaId ?? "")}
              onChange={(e) =>
                setUploadPastaId(e.target.value ? Number(e.target.value) : null)
              }
              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              disabled={uploading}
            >
              <option value="">Raiz (sem pasta)</option>
              {pastas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </select>
            <label
              className={`inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border bg-background px-3 text-xs hover:bg-accent ${
                uploading ? "opacity-50 cursor-wait" : ""
              }`}
            >
              {uploading ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Upload className="size-3.5" />
              )}
              {uploading ? "Enviando…" : "Selecionar arquivos"}
              <input
                type="file"
                accept=".md,.markdown,.pdf,.docx,.txt"
                multiple
                onChange={handleUpload}
                disabled={uploading}
                className="hidden"
              />
            </label>
            <span className="text-[11px] text-muted-foreground">
              .md splita por headers H1/H2 automaticamente
            </span>
            <span className="ml-auto" />
            <Button
              size="sm"
              variant="outline"
              onClick={handleAnalyzeSandbox}
              disabled={analyzing}
              title="Re-roda clusterização sandbox e gera novas sugestões"
            >
              {analyzing ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : null}
              {analyzing ? "Analisando…" : "🧪 Analisar via sandbox"}
            </Button>
          </div>
        </div>


        {error && <p className="text-sm text-destructive">{error}</p>}
        {success && <p className="text-sm text-emerald-300">{success}</p>}

        {/* === FORM PASTA === */}
        {pastaEdit.mode !== "closed" && (
          <form
            onSubmit={handleSubmitPasta}
            className="space-y-3 rounded-md border bg-muted/20 p-4"
          >
            {pastaEdit.mode === "edit" && (
              <input type="hidden" name="id" value={pastaEdit.pasta.id} />
            )}
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Nome
              </label>
              <input
                name="nome"
                defaultValue={
                  pastaEdit.mode === "edit" ? pastaEdit.pasta.nome : ""
                }
                placeholder="FAQ Atendimento"
                required
                maxLength={120}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Pasta pai (opcional)
              </label>
              <select
                name="parent_id"
                defaultValue={
                  pastaEdit.mode === "edit"
                    ? String(pastaEdit.pasta.parent_id ?? "")
                    : ""
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">— Raiz —</option>
                {parentOptions(
                  pastaEdit.mode === "edit" ? pastaEdit.pasta.id : undefined
                ).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Descrição (opcional)
              </label>
              <input
                name="descricao"
                defaultValue={
                  pastaEdit.mode === "edit"
                    ? pastaEdit.pasta.descricao ?? ""
                    : ""
                }
                maxLength={300}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setPastaEdit({ mode: "closed" })}
                disabled={isPending}
              >
                <X className="size-3.5" />
                Cancelar
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending ? "Salvando…" : "Salvar pasta"}
              </Button>
            </div>
          </form>
        )}

        {/* === FORM DOC === */}
        {docEdit.mode !== "closed" && (
          <form
            onSubmit={handleSubmitDoc}
            className="space-y-3 rounded-md border bg-emerald-950/10 p-4"
          >
            {docEdit.mode === "edit" && (
              <input type="hidden" name="id" value={docEdit.doc.id} />
            )}
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Pasta
              </label>
              <select
                name="pasta_id"
                defaultValue={
                  docEdit.mode === "edit"
                    ? String(docEdit.doc.pasta_id ?? "")
                    : docEdit.mode === "create"
                      ? String(docEdit.pastaId ?? "")
                      : ""
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">— Raiz (sem pasta) —</option>
                {pastas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Título
              </label>
              <input
                name="titulo"
                defaultValue={docEdit.mode === "edit" ? docEdit.doc.titulo : ""}
                placeholder="Política de cancelamento"
                required
                maxLength={200}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Conteúdo
              </label>
              <textarea
                name="conteudo"
                defaultValue={
                  docEdit.mode === "edit" ? docEdit.doc.conteudo : ""
                }
                placeholder="Texto que será chunkado + indexado para o RAG…"
                required
                rows={8}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Após salvar, o backend gera embeddings via{" "}
                <code className="font-mono">backfill_chunks</code>.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Tags (separadas por vírgula)
              </label>
              <input
                name="tags"
                defaultValue={
                  docEdit.mode === "edit"
                    ? (docEdit.doc.tags || []).join(", ")
                    : ""
                }
                placeholder="cancelamento, politica"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="ativo"
                  value="true"
                  defaultChecked={
                    docEdit.mode === "edit" ? docEdit.doc.ativo : true
                  }
                  className="size-4 rounded border-input accent-primary"
                />
                Ativo (incluído nas buscas RAG)
              </label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setDocEdit({ mode: "closed" })}
                  disabled={isPending}
                >
                  <X className="size-3.5" />
                  Cancelar
                </Button>
                <Button type="submit" disabled={isPending}>
                  {isPending ? "Salvando…" : "Salvar doc"}
                </Button>
              </div>
            </div>
          </form>
        )}

        {/* === ÁRVORE DE PASTAS COM DOCS === */}
        <div className="rounded-md border">
          {/* Raiz: docs sem pasta */}
          {(() => {
            const rootDocs = docsByPasta.get(null) ?? [];
            const isExpanded = expanded.has(null);
            return (
              <div className="border-b last:border-0">
                <div className="flex items-center justify-between p-2 hover:bg-muted/30">
                  <button
                    type="button"
                    onClick={() => toggleExpand(null)}
                    className="flex flex-1 items-center gap-2 text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                    <Folder className="size-4 text-muted-foreground" />
                    <span className="font-medium">Raiz (sem pasta)</span>
                    {rootDocs.length > 0 && (
                      <Badge variant="outline" className="text-[10px]">
                        {rootDocs.length} doc{rootDocs.length > 1 ? "s" : ""}
                      </Badge>
                    )}
                  </button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      clearMessages();
                      setDocEdit({ mode: "create", pastaId: null });
                    }}
                    disabled={isPending}
                  >
                    <Plus className="size-3.5" />
                  </Button>
                </div>
                {isExpanded && rootDocs.length > 0 && (
                  <div className="bg-muted/10">
                    {rootDocs.map((d) => renderDocItem(d, 2.5))}
                  </div>
                )}
                {isExpanded && rootDocs.length === 0 && (
                  <p className="px-10 pb-3 text-xs text-muted-foreground">
                    Nenhum doc na raiz.
                  </p>
                )}
              </div>
            );
          })()}

          {tree.length === 0 && (
            <p className="p-3 text-sm text-muted-foreground">
              Nenhuma pasta criada. Use &quot;Nova pasta&quot; pra organizar
              docs por setor/agente.
            </p>
          )}

          {tree.map(({ pasta: p, depth }) => {
            const pastaDocs = docsByPasta.get(p.id) ?? [];
            const isExpanded = expanded.has(p.id);
            return (
              <div key={p.id} className="border-b last:border-0">
                <div
                  className="flex items-center justify-between p-2 hover:bg-muted/30"
                  style={{ paddingLeft: `${0.5 + depth * 1.25}rem` }}
                >
                  <button
                    type="button"
                    onClick={() => toggleExpand(p.id)}
                    className="flex flex-1 items-center gap-2 text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                    {depth === 0 ? (
                      <FolderTree className="size-4 text-brand-primary" />
                    ) : (
                      <Folder className="size-4 text-muted-foreground" />
                    )}
                    <span className="font-medium">{p.nome}</span>
                    {p.docs_count !== null && p.docs_count > 0 && (
                      <Badge variant="outline" className="text-[10px]">
                        {p.docs_count} doc{p.docs_count > 1 ? "s" : ""}
                      </Badge>
                    )}
                    {p.descricao && (
                      <span className="truncate text-[11px] text-muted-foreground">
                        — {p.descricao}
                      </span>
                    )}
                  </button>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      title="Adicionar doc nesta pasta"
                      onClick={() => {
                        clearMessages();
                        setDocEdit({ mode: "create", pastaId: p.id });
                      }}
                      disabled={isPending}
                    >
                      <Plus className="size-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        clearMessages();
                        setPastaEdit({ mode: "edit", pasta: p });
                      }}
                      disabled={isPending}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDeletePasta(p)}
                      disabled={isPending}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
                {isExpanded && pastaDocs.length > 0 && (
                  <div className="bg-muted/10">
                    {pastaDocs.map((d) =>
                      renderDocItem(d, 2.5 + depth * 1.25)
                    )}
                  </div>
                )}
                {isExpanded && pastaDocs.length === 0 && (
                  <p
                    className="pb-3 text-xs text-muted-foreground"
                    style={{ paddingLeft: `${3 + depth * 1.25}rem` }}
                  >
                    Vazia.{" "}
                    <button
                      type="button"
                      className="underline hover:text-foreground"
                      onClick={() => {
                        clearMessages();
                        setDocEdit({ mode: "create", pastaId: p.id });
                      }}
                    >
                      Adicionar doc
                    </button>
                  </p>
                )}
              </div>
            );
          })}
        </div>

        <p className="rounded-md border border-dashed p-3 text-[11px] text-muted-foreground">
          <strong>Sprint M:</strong> agentes IA com{" "}
          <code className="font-mono">base_conhecimento_ids</code> configurado
          (em <code className="font-mono">/agents/db/&lt;slug&gt;</code> aba KB)
          buscam apenas nas pastas vinculadas. Sem vínculo = busca em toda a
          empresa.
        </p>
      </CardContent>
    </Card>
  );
}
