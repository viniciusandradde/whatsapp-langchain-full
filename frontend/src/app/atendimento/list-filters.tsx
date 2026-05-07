"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Departamento, TipoVisualizacao } from "@/lib/api";

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
}

export function ListFilters({ tipo, departamentos, depId, prioridade, q }: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [busca, setBusca] = useState(q ?? "");

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

  const hasFiltros = depId || prioridade || q;

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
