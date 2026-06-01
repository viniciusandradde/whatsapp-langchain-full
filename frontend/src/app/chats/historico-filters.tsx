"use client";

import { Download, Filter, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";

type SP = Record<string, string | string[] | undefined>;

const STATUS_OPTS = [
  { v: "aguardando", label: "Aguardando" },
  { v: "em_andamento", label: "Em andamento" },
  { v: "resolvido", label: "Resolvido" },
  { v: "abandonado", label: "Abandonado" },
];
const PRIORIDADE_OPTS = ["baixa", "media", "alta", "urgente"];

function first(v: string | string[] | undefined): string {
  return (Array.isArray(v) ? v[0] : v) ?? "";
}
function many(v: string | string[] | undefined): string[] {
  if (v === undefined) return [];
  return Array.isArray(v) ? v : [v];
}

export function HistoricoFilters({
  deptos,
  conexoes,
  tags,
  current,
}: {
  deptos: { id: number; nome: string }[];
  conexoes: { id: number; label: string }[];
  tags: { id: number; nome: string; cor: string | null }[];
  current: SP;
}) {
  const router = useRouter();

  const [createdDe, setCreatedDe] = useState(first(current.created_de));
  const [createdAte, setCreatedAte] = useState(first(current.created_ate));
  const [status, setStatus] = useState<string[]>(many(current.status));
  const [conexaoId, setConexaoId] = useState(first(current.conexao_id));
  const [departamentoId, setDepartamentoId] = useState(
    first(current.departamento_id)
  );
  const [tagId, setTagId] = useState(first(current.tag_id));
  const [prioridade, setPrioridade] = useState(first(current.prioridade));
  const [q, setQ] = useState(first(current.q));

  function buildQS(): string {
    const p = new URLSearchParams();
    if (createdDe) p.set("created_de", createdDe);
    if (createdAte) p.set("created_ate", createdAte);
    for (const s of status) p.append("status", s);
    if (conexaoId) p.set("conexao_id", conexaoId);
    if (departamentoId) p.set("departamento_id", departamentoId);
    if (tagId) p.set("tag_id", tagId);
    if (prioridade) p.set("prioridade", prioridade);
    if (q.trim()) p.set("q", q.trim());
    // preserva ordenação se houver
    if (first(current.sort_field)) p.set("sort_field", first(current.sort_field));
    if (first(current.sort_order)) p.set("sort_order", first(current.sort_order));
    return p.toString();
  }

  function aplicar() {
    router.push(`/chats?${buildQS()}`);
  }
  function limpar() {
    router.push("/chats");
  }
  function toggleStatus(v: string) {
    setStatus((cur) =>
      cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
    );
  }

  const exportQS = buildQS();

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      {/* Linha 1: período + busca */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-xs text-muted-foreground">
          De
          <input
            type="date"
            value={createdDe}
            onChange={(e) => setCreatedDe(e.target.value)}
            className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs text-muted-foreground">
          Até
          <input
            type="date"
            value={createdAte}
            onChange={(e) => setCreatedAte(e.target.value)}
            className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs text-muted-foreground lg:col-span-2">
          Busca (protocolo, cliente, telefone, conteúdo)
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && aplicar()}
            placeholder="Buscar..."
            className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      {/* Linha 2: selects */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Select
          label="Canal"
          value={conexaoId}
          onChange={setConexaoId}
          options={conexoes.map((c) => ({ v: String(c.id), label: c.label }))}
        />
        <Select
          label="Departamento"
          value={departamentoId}
          onChange={setDepartamentoId}
          options={deptos.map((d) => ({ v: String(d.id), label: d.nome }))}
        />
        <Select
          label="Tag"
          value={tagId}
          onChange={setTagId}
          options={tags.map((t) => ({ v: String(t.id), label: t.nome }))}
        />
        <Select
          label="Prioridade"
          value={prioridade}
          onChange={setPrioridade}
          options={PRIORIDADE_OPTS.map((p) => ({ v: p, label: p }))}
        />
      </div>

      {/* Linha 3: status (multi) */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Status:</span>
        {STATUS_OPTS.map((s) => (
          <button
            key={s.v}
            type="button"
            onClick={() => toggleStatus(s.v)}
            className={`rounded-full border px-3 py-1 text-xs transition ${
              status.includes(s.v)
                ? "border-primary bg-primary/10 text-primary"
                : "border-muted text-muted-foreground hover:bg-muted"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Ações */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" onClick={aplicar}>
          <Filter className="mr-1.5 h-4 w-4" /> Filtrar
        </Button>
        <Button size="sm" variant="outline" onClick={limpar}>
          <X className="mr-1.5 h-4 w-4" /> Limpar
        </Button>
        <div className="ml-auto flex gap-2">
          <a
            href={`/api/historico-export?formato=csv${exportQS ? `&${exportQS}` : ""}`}
            className="inline-flex items-center rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
          >
            <Download className="mr-1.5 h-4 w-4" /> CSV
          </a>
          <a
            href={`/api/historico-export?formato=xlsx${exportQS ? `&${exportQS}` : ""}`}
            className="inline-flex items-center rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
          >
            <Download className="mr-1.5 h-4 w-4" /> Excel
          </a>
        </div>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { v: string; label: string }[];
}) {
  return (
    <label className="text-xs text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm capitalize"
      >
        <option value="">Todos</option>
        {options.map((o) => (
          <option key={o.v} value={o.v}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
