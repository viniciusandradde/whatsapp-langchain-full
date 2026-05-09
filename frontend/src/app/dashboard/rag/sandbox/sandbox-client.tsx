"use client";

/**
 * SandboxClient — Sprint S.1.
 *
 * Lista cards de sugestões de cluster com botões aprovar/rejeitar.
 * Optimistic UI: card some imediatamente, server action valida.
 * Suporta bulk approve com confirm.
 */

import { useState, useTransition } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Sparkles,
  Upload,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { RagSuggestion } from "@/lib/api";

import {
  applyCleanAction,
  approveSuggestionAction,
  bulkApproveAction,
  importDatasetAction,
  previewCleanAction,
  rejectSuggestionAction,
} from "./actions";

interface Props {
  initialSuggestions: RagSuggestion[];
}

export function SandboxClient({ initialSuggestions }: Props) {
  const [suggestions, setSuggestions] = useState(initialSuggestions);
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [statusFilter, setStatusFilter] = useState<
    "pending" | "approved" | "rejected"
  >("pending");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isBulkPending, startBulkTransition] = useTransition();
  const [importing, setImporting] = useState(false);
  const [cleanPreview, setCleanPreview] = useState<{
    total: number;
    greetings: number;
    low_value: number;
    duplicates: number;
    will_disable: number;
  } | null>(null);
  const [cleaning, setCleaning] = useState(false);

  function clearMessages() {
    setError(null);
    setSuccess(null);
  }

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleApprove(id: number) {
    clearMessages();
    setPendingIds((prev) => new Set(prev).add(id));
    const r = await approveSuggestionAction(id);
    setPendingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (!r.ok) {
      setError(`Falha aprovar #${id}: ${r.error}`);
      return;
    }
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
    setSuccess(`Sugestão #${id} aprovada → documento #${r.docId} criado`);
  }

  async function handleReject(id: number) {
    clearMessages();
    setPendingIds((prev) => new Set(prev).add(id));
    const r = await rejectSuggestionAction(id);
    setPendingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (!r.ok) {
      setError(`Falha rejeitar #${id}: ${r.error}`);
      return;
    }
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
    setSuccess(`Sugestão #${id} rejeitada`);
  }

  async function handlePreviewClean() {
    clearMessages();
    setCleaning(true);
    const r = await previewCleanAction();
    setCleaning(false);
    if (!r.ok) {
      setError(`Falha preview: ${r.error}`);
      return;
    }
    setCleanPreview({
      total: r.total,
      greetings: r.greetings,
      low_value: r.low_value,
      duplicates: r.duplicates,
      will_disable: r.will_disable,
    });
  }

  async function handleApplyClean() {
    if (!cleanPreview) return;
    if (
      !confirm(
        `Marcar ${cleanPreview.will_disable} mensagens como 'disabled'?\n\n` +
          `(Reversível via UPDATE manual no DB. Não deleta.)`
      )
    )
      return;
    clearMessages();
    setCleaning(true);
    const r = await applyCleanAction();
    setCleaning(false);
    if (!r.ok) {
      setError(`Falha aplicar: ${r.error}`);
      return;
    }
    setCleanPreview(null);
    setSuccess(
      `🧹 Limpeza aplicada: ${r.will_disable} desativadas (${r.greetings} saudações, ${r.low_value} baixo valor, ${r.duplicates} dupes)`
    );
  }

  async function handleImportDataset(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    clearMessages();
    setImporting(true);
    const fd = new FormData();
    fd.set("arquivo", file, file.name);
    const r = await importDatasetAction(fd);
    setImporting(false);
    e.target.value = "";
    if (!r.ok) {
      setError(`Falha import: ${r.error}`);
      return;
    }
    setSuccess(
      `📥 ${r.received} linhas recebidas → fewshot ${r.inserted_fewshot}, log ${r.inserted_querylog}, skip ${r.skipped}` +
        (r.errors.length > 0 ? ` (${r.errors.length} erros)` : "")
    );
  }

  function handleBulkApprove() {
    clearMessages();
    if (suggestions.length === 0) return;
    if (
      !confirm(
        `Aprovar TODAS as ${suggestions.length} sugestões?\n\n` +
          `Cada uma vira um documento_conhecimento + chunks + embeddings ` +
          `(custo OpenAI proporcional).`
      )
    )
      return;

    const ids = suggestions.map((s) => s.id);
    startBulkTransition(async () => {
      const r = await bulkApproveAction(ids);
      if (r.failed === 0) {
        setSuccess(`✅ ${r.success} sugestões aprovadas`);
        setSuggestions([]);
      } else {
        setError(
          `${r.success} aprovadas / ${r.failed} falharam:\n${r.errors.slice(0, 3).join("\n")}`
        );
      }
    });
  }

  // Agrupa por pasta_nome
  const byPasta = new Map<string, RagSuggestion[]>();
  for (const s of suggestions) {
    const k = s.pasta_nome || "(sem pasta)";
    const arr = byPasta.get(k) || [];
    arr.push(s);
    byPasta.set(k, arr);
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">
              Sugestões de KB ({suggestions.length})
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Cada sugestão é um cluster de mensagens reais que precisam de
              FAQ. Aprovar cria <code>documento_conhecimento</code>.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(["pending", "approved", "rejected"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatusFilter(s)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  s === statusFilter
                    ? "border-primary bg-primary/10 text-primary"
                    : "hover:bg-accent"
                }`}
              >
                {s === "pending"
                  ? "Pendentes"
                  : s === "approved"
                    ? "Aprovadas"
                    : "Rejeitadas"}
              </button>
            ))}
            {statusFilter === "pending" && suggestions.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleBulkApprove}
                disabled={isBulkPending}
              >
                {isBulkPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="size-3.5" />
                )}
                Aprovar todas
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive whitespace-pre-wrap">
            {error}
          </p>
        )}
        {success && (
          <p className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-3 text-sm text-emerald-300">
            {success}
          </p>
        )}

        <div className="grid gap-3 lg:grid-cols-2">
          {/* Sprint S.4 — Upload dataset JSONL/CSV */}
          <div className="rounded-md border border-amber-500/30 bg-amber-950/10 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Upload className="size-4 text-amber-400" />
              <span className="text-sm font-medium">Importar dataset</span>
            </div>
            <label
              className={`inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border bg-background px-3 text-xs hover:bg-accent ${
                importing ? "opacity-50 cursor-wait" : ""
              }`}
            >
              {importing ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Upload className="size-3.5" />
              )}
              {importing ? "Importando…" : "Selecionar JSONL/CSV"}
              <input
                type="file"
                accept=".jsonl,.json,.csv"
                onChange={handleImportDataset}
                disabled={importing}
                className="hidden"
              />
            </label>
            <p className="mt-2 text-[11px] text-muted-foreground">
              agente_slug, cliente_msg, agente_resposta, outcome
            </p>
          </div>

          {/* Sprint S.5 — Limpeza dataset */}
          <div className="rounded-md border border-purple-500/30 bg-purple-950/10 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="size-4 text-purple-400" />
              <span className="text-sm font-medium">Limpar dataset</span>
            </div>
            {cleanPreview ? (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-1 text-[11px]">
                  <span>Total ativo:</span>
                  <span className="text-right font-mono">{cleanPreview.total}</span>
                  <span>Saudações:</span>
                  <span className="text-right font-mono">{cleanPreview.greetings}</span>
                  <span>Baixo valor:</span>
                  <span className="text-right font-mono">{cleanPreview.low_value}</span>
                  <span>Duplicatas:</span>
                  <span className="text-right font-mono">{cleanPreview.duplicates}</span>
                  <span className="font-semibold">Será desativado:</span>
                  <span className="text-right font-mono font-semibold">
                    {cleanPreview.will_disable}
                  </span>
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    onClick={handleApplyClean}
                    disabled={cleaning || cleanPreview.will_disable === 0}
                  >
                    {cleaning ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                    Aplicar
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setCleanPreview(null)}
                    disabled={cleaning}
                  >
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={handlePreviewClean}
                disabled={cleaning}
              >
                {cleaning ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                Preview
              </Button>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">
              Marca status='disabled' (reversível). Não deleta.
            </p>
          </div>
        </div>


        {suggestions.length === 0 ? (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            Nenhuma sugestão {statusFilter}.{" "}
            {statusFilter !== "pending" && (
              <>
                Para gerar, rode{" "}
                <code className="font-mono text-xs">
                  scripts/cluster_hospitalar.py
                </code>
                .
              </>
            )}
          </p>
        ) : (
          <div className="space-y-4">
            {Array.from(byPasta.entries()).map(([pastaNome, items]) => (
              <div key={pastaNome} className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {pastaNome}{" "}
                  <span className="font-normal">({items.length})</span>
                </h3>
                {items.map((s) => {
                  const isExpanded = expanded.has(s.id);
                  const isPending = pendingIds.has(s.id);
                  return (
                    <div
                      key={s.id}
                      className="rounded-md border bg-muted/10 p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <button
                          type="button"
                          onClick={() => toggleExpand(s.id)}
                          className="flex flex-1 items-start gap-2 text-left"
                        >
                          {isExpanded ? (
                            <ChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="font-medium">{s.titulo}</p>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className="text-[10px]">
                                {s.cluster_size} msgs
                              </Badge>
                              <Badge variant="secondary" className="text-[10px]">
                                #{s.id}
                              </Badge>
                            </div>
                          </div>
                        </button>
                        <div className="flex shrink-0 gap-1">
                          <Button
                            size="sm"
                            variant="default"
                            onClick={() => handleApprove(s.id)}
                            disabled={isPending}
                          >
                            {isPending ? (
                              <Loader2 className="size-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="size-3.5" />
                            )}
                            Aprovar
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleReject(s.id)}
                            disabled={isPending}
                          >
                            <XCircle className="size-3.5" />
                          </Button>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="mt-3 space-y-2 border-t pt-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                              Conteúdo proposto
                            </p>
                            <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
                              {s.conteudo_draft}
                            </p>
                          </div>
                          {s.queries_amostra.length > 0 && (
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                Queries do cluster ({s.queries_amostra.length})
                              </p>
                              <ul className="mt-1 space-y-0.5">
                                {s.queries_amostra
                                  .slice(0, 8)
                                  .map((q, i) => (
                                    <li
                                      key={i}
                                      className="rounded bg-background px-2 py-1 text-xs text-muted-foreground"
                                    >
                                      • {q}
                                    </li>
                                  ))}
                                {s.queries_amostra.length > 8 && (
                                  <li className="px-2 text-[10px] text-muted-foreground">
                                    + {s.queries_amostra.length - 8} mais
                                  </li>
                                )}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
