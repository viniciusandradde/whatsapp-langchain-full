"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Search, Tag as TagIcon, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Departamento, Tag, TipoVisualizacao } from "@/lib/api";

import { loadTagsAction } from "./actions";
import { TagChip } from "./tag-chip";

const PRIORIDADES = [
  { v: "urgente", l: "Urgente" },
  { v: "alta", l: "Alta" },
  { v: "media", l: "Média" },
  { v: "baixa", l: "Baixa" },
] as const;

const inputCls =
  "h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";

interface Props {
  tipo: TipoVisualizacao;
  departamentos: Departamento[];
  depId?: number;
  prioridade?: "baixa" | "media" | "alta" | "urgente";
  q?: string;
  tagIds?: number[];
}

export function ListFilters({
  tipo,
  departamentos,
  depId,
  prioridade,
  q,
  tagIds = [],
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [busca, setBusca] = useState(q ?? "");
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagOpen, setTagOpen] = useState(false);

  useEffect(() => {
    loadTagsAction(true).then((r) => {
      if (r.ok) setTags(r.tags);
    });
  }, []);

  const setParam = (key: string, value: string | undefined) => {
    const params = new URLSearchParams(sp.toString());
    if (value === undefined || value === "") {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    if (!params.get("tipo")) params.set("tipo", tipo);
    router.push(`/atendimento?${params.toString()}`);
  };

  const submitBusca = (e: React.FormEvent) => {
    e.preventDefault();
    setParam("q", busca.trim() || undefined);
  };

  const toggleTag = (id: number) => {
    const params = new URLSearchParams(sp.toString());
    const current = params.getAll("tag_id").map(Number);
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    params.delete("tag_id");
    for (const n of next) params.append("tag_id", String(n));
    if (!params.get("tipo")) params.set("tipo", tipo);
    router.push(`/atendimento?${params.toString()}`);
  };

  const hasFiltros = depId || prioridade || q || tagIds.length > 0;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 p-3">
      <select
        value={depId ?? ""}
        onChange={(e) => setParam("dep_id", e.target.value || undefined)}
        className={inputCls}
        aria-label="Filtrar por departamento"
      >
        <option value="">Todos os departamentos</option>
        {departamentos
          .filter((d) => d.ativo)
          .map((d) => (
            <option key={d.id} value={d.id}>
              {d.nome}
            </option>
          ))}
      </select>

      <select
        value={prioridade ?? ""}
        onChange={(e) => setParam("prioridade", e.target.value || undefined)}
        className={inputCls}
        aria-label="Filtrar por prioridade"
      >
        <option value="">Todas as prioridades</option>
        {PRIORIDADES.map((p) => (
          <option key={p.v} value={p.v}>
            {p.l}
          </option>
        ))}
      </select>

      <form onSubmit={submitBusca} className="flex items-center gap-1">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar nome ou protocolo…"
            className={`${inputCls} pl-8 w-56`}
          />
        </div>
        <Button type="submit" size="sm" variant="outline">
          Buscar
        </Button>
      </form>

      {tags.length > 0 && (
        <div className="relative">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-9 gap-1"
            onClick={() => setTagOpen((v) => !v)}
          >
            <TagIcon className="h-3.5 w-3.5" />
            Tags
            {tagIds.length > 0 && (
              <span className="ml-1 rounded-full bg-brand-primary/15 px-1.5 text-xs">
                {tagIds.length}
              </span>
            )}
          </Button>
          {tagOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setTagOpen(false)}
              />
              <div className="absolute right-0 z-50 mt-1 w-60 rounded-lg border bg-popover p-2 shadow-lg">
                <ul className="max-h-64 space-y-0.5 overflow-y-auto">
                  {tags.map((t) => {
                    const on = tagIds.includes(t.id);
                    return (
                      <li key={t.id}>
                        <button
                          type="button"
                          onClick={() => toggleTag(t.id)}
                          className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                        >
                          <TagChip nome={t.nome} cor={t.cor} size="sm" />
                          {on && <span className="text-brand-primary">✓</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </>
          )}
        </div>
      )}

      {hasFiltros && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setBusca("");
            router.push(`/atendimento?tipo=${tipo}`);
          }}
        >
          <X className="size-3.5" />
          Limpar
        </Button>
      )}
    </div>
  );
}
