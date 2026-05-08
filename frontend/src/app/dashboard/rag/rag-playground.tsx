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

interface Props {
  pastas: Pasta[];
}

export function RagPlayground({ pastas }: Props) {
  const [query, setQuery] = useState("");
  const [selectedPastas, setSelectedPastas] = useState<Set<number>>(new Set());
  const [hits, setHits] = useState<PreviewHit[] | null>(null);
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
        }),
        credentials: "include",
      });
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`${r.status}: ${txt}`);
      }
      const data = (await r.json()) as PreviewHit[];
      setHits(data);
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

          <div className="flex justify-end">
            <Button type="submit" disabled={loading || !query.trim()}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Beaker className="size-4" />
              )}
              Buscar
            </Button>
          </div>
        </form>

        {error && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        )}

        {hits !== null && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              {hits.length === 0
                ? "Nenhum hit. Considere criar um doc cobrindo essa query."
                : `${hits.length} resultado(s) — ordenados por relevância.`}
            </p>
            {hits.map((h, i) => (
              <div
                key={`${h.doc_id}-${h.chunk_idx}`}
                className="rounded-md border bg-muted/20 p-3 text-sm"
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      #{i + 1}
                    </span>
                    <p className="font-medium">{h.titulo}</p>
                    <Badge variant="outline" className="text-[10px]">
                      doc {h.doc_id} · chunk {h.chunk_idx}
                    </Badge>
                  </div>
                  <Badge
                    variant={
                      h.score > 0.7
                        ? "default"
                        : h.score > 0.4
                          ? "secondary"
                          : "outline"
                    }
                    className="text-[10px]"
                  >
                    {h.score.toFixed(3)}
                  </Badge>
                </div>
                {h.reason && (
                  <p className="mb-1 text-[11px] italic text-muted-foreground">
                    Reason: {h.reason}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">{h.snippet}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
