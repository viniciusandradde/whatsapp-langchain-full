"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Tag as TagIcon, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  AtendenteStatus,
  Departamento,
  Tag,
  TipoVisualizacao,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { loadAtendentesAction, loadTagsAction } from "./actions";
import { TagChip } from "./tag-chip";

const PRIORIDADES = [
  { v: "urgente", l: "Urgente" },
  { v: "alta", l: "Alta" },
  { v: "media", l: "Média" },
  { v: "baixa", l: "Baixa" },
] as const;

// `px-2` no celular: na grade de 2 colunas a 390px, "Todos departamentos"
// perdia a última letra com os 12px de cada lado.
const inputCls =
  "h-9 rounded-md border border-input bg-transparent px-2 py-1 text-[13px] shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring md:px-3 md:text-sm";

interface Props {
  tipo: TipoVisualizacao;
  departamentos: Departamento[];
  depId?: number;
  prioridade?: "baixa" | "media" | "alta" | "urgente";
  q?: string;
  tagIds?: number[];
  assignedTo?: string;
  className?: string;
}

export function ListFilters({
  tipo,
  departamentos,
  depId,
  prioridade,
  q,
  tagIds = [],
  assignedTo,
  className,
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagOpen, setTagOpen] = useState(false);
  const [atendentes, setAtendentes] = useState<AtendenteStatus[]>([]);

  useEffect(() => {
    loadTagsAction(true).then((r) => {
      if (r.ok) setTags(r.tags);
    });
    loadAtendentesAction().then((r) => {
      if (r.ok) setAtendentes(r.atendentes);
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

  const hasFiltros =
    depId || prioridade || q || tagIds.length > 0 || assignedTo;

  return (
    // Toolbar inline (sem moldura): divide a linha com o título da página.
    // No celular vira grade de DUAS colunas (pedido do dono, 2026-09-18): os
    // três selects empilhados um por linha comiam meia tela antes da fila.
    <div
      className={cn(
        "grid w-full grid-cols-2 gap-2 md:flex md:w-auto md:flex-wrap md:items-center",
        className
      )}
    >
      <select
        value={depId ?? ""}
        onChange={(e) => setParam("dep_id", e.target.value || undefined)}
        className={cn(inputCls, "w-full md:w-auto")}
        aria-label="Filtrar por departamento"
      >
        <option value="">Todos departamentos</option>
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
        className={cn(inputCls, "w-full md:w-auto")}
        aria-label="Filtrar por prioridade"
      >
        <option value="">Todas prioridades</option>
        {PRIORIDADES.map((p) => (
          <option key={p.v} value={p.v}>
            {p.l}
          </option>
        ))}
      </select>

      {/* Filtro por responsável — supervisor vê a carteira de um atendente
          (inclusive offline). Select do kit, não elemento cru (form_cru). */}
      {atendentes.length > 0 && (
        <Select
          value={assignedTo ?? null}
          onValueChange={(v) =>
            setParam("assigned_to", (v as string | null) ?? undefined)
          }
        >
          <SelectTrigger
            className="h-9 w-full md:w-48"
            aria-label="Filtrar por responsável"
          >
            <SelectValue>
              {(v: string | null) => {
                if (!v) return "Todos responsáveis";
                const a = atendentes.find((x) => x.user_id === v);
                return a?.nome || a?.email || "Responsável";
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={null}>Todos responsáveis</SelectItem>
            {atendentes.map((a) => (
              <SelectItem key={a.user_id} value={a.user_id}>
                {a.nome || a.email || a.user_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* A busca (nome, telefone ou protocolo) mora na toolbar da lista
          (`lista-toolbar.tsx`) desde o inbox agrupado — `q` continua sendo
          um param da URL e entra no "Limpar" daqui. */}

      {tags.length > 0 && (
        <div className="relative">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-9 w-full gap-1 md:w-auto"
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
          className="w-full md:w-auto"
          onClick={() => {
            const id = sp.get("id");
            router.push(`/atendimento?tipo=${tipo}${id ? `&id=${id}` : ""}`);
          }}
        >
          <X className="size-3.5" />
          Limpar
        </Button>
      )}
    </div>
  );
}
