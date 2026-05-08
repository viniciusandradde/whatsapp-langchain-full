"use client";

import { useState } from "react";
import { Beaker, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Pasta, PreviewHit } from "@/lib/api";

type SearchMode = "vector" | "hybrid" | "hybrid_hyde";

interface PreviewModeResult {
  mode: SearchMode;
  hyde_query: string | null;
  duracao_ms: number;
  hits: PreviewHit[];
}

interface Props {
  pastas: Pasta[];
}

const MODE_LABELS: Record<SearchMode, string> = {
  vector: "Vector (cosine)",
  hybrid: "Hybrid (RRF)",
  hybrid_hyde: "Hybrid + HyDE",
};

export function RagPlayground({ pastas }: Props) {
  const [query, setQuery] = useState("");
  const [selectedPastas, setSelectedPastas] = useState<Set<number>>(new Set());
  const [selectedModes, setSelectedModes] = useState<Set<SearchMode>>(
    () => new Set<SearchMode>(["hybrid"])
  );
  const [results, setResults] = useState<PreviewModeResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function togglePasta(id: number) {
    setSelectedPastas((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleMode(m: SearchMode) {
    setSelectedModes((prev) => {
      const next = new Set(prev);
      if (next.has(m)) {
        if (next.size > 1) next.delete(m);
      } else {
        next.add(m);
      }
      return next;
    });
  }

  async function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await fetch("/api/proxy/admin-rag/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          pasta_ids:
            selectedPastas.size > 0 ? Array.from(selectedPastas) : null,
          modes: Array.from(selectedModes),
        }),
        credentials: "include",
      });
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`${r.status}: ${txt}`);
      }
      const data = (await r.json()) as PreviewModeResult[];
      setResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro inesperado.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Beaker className="size-4" />
          Playground — testar busca
        </CardTitle>
        <p className="text-[11px] text-muted-foreground">
          Simula a tool <code className="font-mono">search_knowledge_base</code>
          {" "}sem chamar o agente. Útil pra ajustar docs/pastas e ver score.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSearch} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
              Query
            </label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ex: como cancelar agendamento? quais convênios aceitam?"
              required
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          {pastas.length > 0 && (
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                Filtrar por pastas (vazio = todas)
              </label>
              <div className="flex flex-wrap gap-1">
                {pastas.map((p) => {
                  const isSelected = selectedPastas.has(p.id);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => togglePasta(p.id)}
                      className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                        isSelected
                          ? "border-primary bg-primary/10 text-primary"
                          : "hover:bg-accent"
                      }`}
                    >
                      {p.nome}
                      {p.docs_count !== null && (
                        <span className="ml-1 text-[10px] opacity-60">
                          ({p.docs_count})
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
              Modos de busca (compare lado a lado)
            </label>
            <div className="flex flex-wrap gap-1">
              {(Object.keys(MODE_LABELS) as SearchMode[]).map((m) => {
                const isSelected = selectedModes.has(m);
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => toggleMode(m)}
                    className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                      isSelected
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                        : "hover:bg-accent"
                    }`}
                  >
                    {MODE_LABELS[m]}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex justify-end">
            <Button type="submit" disabled={loading || !query.trim()}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Beaker className="size-4" />
              )}
              Buscar ({selectedModes.size} modo{selectedModes.size > 1 ? "s" : ""})
            </Button>
          </div>
        </form>

        {error && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        )}

        {results !== null && results.length > 0 && (
          <div
            className={`grid gap-3 ${results.length === 1 ? "grid-cols-1" : results.length === 2 ? "lg:grid-cols-2" : "lg:grid-cols-3"}`}
          >
            {results.map((mr) => (
              <div
                key={mr.mode}
                className="space-y-2 rounded-md border bg-muted/10 p-3"
              >
                <div className="flex items-center justify-between border-b pb-2">
                  <h3 className="text-sm font-semibold">
                    {MODE_LABELS[mr.mode]}
                  </h3>
                  <Badge variant="outline" className="text-[10px]">
                    {mr.duracao_ms}ms · {mr.hits.length} hit
                    {mr.hits.length !== 1 ? "s" : ""}
                  </Badge>
                </div>
                {mr.hyde_query && (
                  <div className="rounded border border-dashed bg-amber-50/30 p-2 text-[11px] dark:bg-amber-950/20">
                    <span className="font-semibold">HyDE:</span>{" "}
                    <span className="text-muted-foreground">
                      {mr.hyde_query.length > 200
                        ? mr.hyde_query.slice(0, 200) + "…"
                        : mr.hyde_query}
                    </span>
                  </div>
                )}
                {mr.hits.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Nenhum hit. Considere criar doc cobrindo essa query.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {mr.hits.map((h, i) => (
                      <div
                        key={`${h.doc_id}-${h.chunk_idx}`}
                        className="rounded-md border bg-background p-2 text-sm"
                      >
                        <div className="mb-1 flex items-start justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1.5">
                            <span className="text-xs text-muted-foreground">
                              #{i + 1}
                            </span>
                            <p className="truncate font-medium text-xs">
                              {h.titulo}
                            </p>
                          </div>
                          <Badge
                            variant={
                              h.score > 0.7
                                ? "default"
                                : h.score > 0.4
                                  ? "secondary"
                                  : "outline"
                            }
                            className="shrink-0 text-[10px]"
                          >
                            {h.score.toFixed(3)}
                          </Badge>
                        </div>
                        {h.reason && (
                          <p className="mb-1 text-[10px] italic text-muted-foreground">
                            {h.reason}
                          </p>
                        )}
                        <p className="text-[11px] text-muted-foreground">
                          {h.snippet}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
