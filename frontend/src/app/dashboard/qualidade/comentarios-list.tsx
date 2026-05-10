"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { NPSAvaliacaoItem } from "@/lib/api";

import { loadAvaliacoesAction } from "./actions";

type Categoria = "promotor" | "neutro" | "detrator";

const FILTERS: { v: Categoria | "todos"; label: string; cls: string }[] = [
  { v: "detrator", label: "Detratores", cls: "text-red-600 dark:text-red-400" },
  { v: "neutro", label: "Neutros", cls: "text-amber-600 dark:text-amber-400" },
  { v: "promotor", label: "Promotores", cls: "text-emerald-600 dark:text-emerald-400" },
  { v: "todos", label: "Todas", cls: "" },
];

const PAGE_SIZE = 20;

interface Props {
  periodo: number;
}

export function ComentariosList({ periodo }: Props) {
  const [filter, setFilter] = useState<Categoria | "todos">("detrator");
  const [pagina, setPagina] = useState(1);
  const [items, setItems] = useState<NPSAvaliacaoItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    loadAvaliacoesAction({
      periodo,
      categoria: filter === "todos" ? undefined : filter,
      pagina,
      limit: PAGE_SIZE,
    })
      .then((r) => {
        if (r.ok) {
          setItems(r.data.items);
          setTotal(r.data.total);
        } else setError(r.error);
      })
      .finally(() => setLoading(false));
  }, [periodo, filter, pagina]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Avaliações com comentário</CardTitle>
        <div className="flex flex-wrap gap-1 text-xs">
          {FILTERS.map((f) => (
            <button
              key={f.v}
              onClick={() => {
                setFilter(f.v);
                setPagina(1);
              }}
              className={`rounded px-2 py-1 ${
                filter === f.v
                  ? "bg-primary text-primary-foreground"
                  : "border bg-background hover:bg-muted"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="rounded border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {loading && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Carregando…
          </p>
        )}
        {!loading && items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Nenhuma avaliação no período/filtro.
          </p>
        )}
        {!loading && items.length > 0 && (
          <div className="space-y-3">
            {items.map((it) => (
              <div
                key={it.id}
                className="rounded-lg border bg-muted/20 p-3 text-sm"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge
                    variant={
                      it.categoria === "promotor"
                        ? "default"
                        : it.categoria === "detrator"
                          ? "destructive"
                          : "secondary"
                    }
                  >
                    {it.categoria === "promotor"
                      ? `🟢 ${it.nota}`
                      : it.categoria === "detrator"
                        ? `🔴 ${it.nota}`
                        : `🟡 ${it.nota}`}
                  </Badge>
                  <span>
                    {new Date(it.created_at).toLocaleString("pt-BR")}
                  </span>
                  {it.protocolo && (
                    <span className="font-mono">#{it.protocolo}</span>
                  )}
                  {it.cliente_nome && <span>· {it.cliente_nome}</span>}
                  {it.departamento_nome && (
                    <span>· {it.departamento_nome}</span>
                  )}
                  {it.atendente_nome && <span>· {it.atendente_nome}</span>}
                </div>
                <p className="text-foreground">
                  {it.comentario || (
                    <span className="italic text-muted-foreground">
                      (sem comentário)
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Página {pagina} de {totalPages} · {total} total
            </span>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={pagina <= 1}
                onClick={() => setPagina((p) => p - 1)}
              >
                Anterior
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={pagina >= totalPages}
                onClick={() => setPagina((p) => p + 1)}
              >
                Próxima
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
