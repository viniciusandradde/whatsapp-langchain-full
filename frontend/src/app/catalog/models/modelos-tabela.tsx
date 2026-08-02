"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Brain, Lock, Pencil, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ModeloLLM } from "@/lib/api";

const TIPO_LABEL: Record<ModeloLLM["tipo"], string> = {
  chat: "Conversa",
  embedding: "Busca semântica",
  midia: "Mídia",
  audio: "Áudio",
  imagem: "Imagem",
};

const FILTRO_TIPO: Record<string, string> = {
  todos: "Todos os tipos",
  chat: "Conversa",
  embedding: "Busca semântica",
  imagem: "Imagem",
  audio: "Áudio",
  midia: "Mídia",
};

type Coluna = "nome" | "entrada" | "saida" | "contexto";

/**
 * Antes esta tela eram 18 cards num grid de três colunas, 4.220px de rolagem.
 *
 * O motivo de alguém abrir aqui é **comparar** — custo de entrada, custo de
 * saída, tamanho da janela — e card em grid é a forma que mais atrapalha
 * comparação: os números ficam em posições diferentes da tela e o olho não
 * consegue percorrer uma coluna. Tabela ordenável resolve o que a tela é.
 */
export function ModelosTabela({ itens }: { itens: ModeloLLM[] }) {
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("todos");
  const [coluna, setColuna] = useState<Coluna>("nome");
  const [asc, setAsc] = useState(true);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const base = itens.filter((m) => {
      if (tipo !== "todos" && m.tipo !== tipo) return false;
      if (!q) return true;
      return (
        m.nome.toLowerCase().includes(q) ||
        m.provedor.toLowerCase().includes(q) ||
        (m.descricao ?? "").toLowerCase().includes(q)
      );
    });

    // Nulo sempre no fim, independente da direção: "sem preço informado" não é
    // "o mais barato".
    const valor = (m: ModeloLLM): number | string => {
      if (coluna === "nome") return `${m.provedor}/${m.nome}`;
      if (coluna === "entrada") return m.custo_input_mtok ?? Infinity;
      if (coluna === "saida") return m.custo_output_mtok ?? Infinity;
      return m.janela_contexto ?? -Infinity;
    };

    return [...base].sort((a, b) => {
      const va = valor(a);
      const vb = valor(b);
      if (typeof va === "string" || typeof vb === "string") {
        return asc
          ? String(va).localeCompare(String(vb))
          : String(vb).localeCompare(String(va));
      }
      if (va === vb) return 0;
      // Infinity marca "sem dado" e fica no fim nos dois sentidos.
      if (!Number.isFinite(va)) return 1;
      if (!Number.isFinite(vb)) return -1;
      return asc ? va - vb : vb - va;
    });
  }, [itens, busca, tipo, coluna, asc]);

  function ordenarPor(c: Coluna) {
    if (c === coluna) {
      setAsc(!asc);
      return;
    }
    setColuna(c);
    // Nome começa A→Z; número começa do menor custo / maior contexto, que é
    // o que a pessoa quer ver primeiro nos dois casos.
    setAsc(c !== "contexto");
  }

  const custom = filtrados.filter((m) => m.empresa_id !== null).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar modelo ou provedor…"
            className="w-72 pl-9"
            aria-label="Buscar modelo"
          />
        </div>
        <Select value={tipo} onValueChange={(v) => setTipo(v ?? "todos")}>
          <SelectTrigger className="h-9 w-48" aria-label="Filtrar por tipo">
            <SelectValue>
              {(v: string | null) => FILTRO_TIPO[v ?? "todos"]}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(FILTRO_TIPO).map(([v, label]) => (
              <SelectItem key={v} value={v}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">
          {filtrados.length} de {itens.length} modelos
          {custom > 0 && ` · ${custom} desta empresa`}
        </span>
      </div>

      {filtrados.length === 0 ? (
        <EmptyState
          icon={Brain}
          title="Nenhum modelo com esse filtro"
          description="Ajuste a busca ou volte para todos os tipos."
          action={{
            label: "Limpar filtros",
            onClick: () => {
              setBusca("");
              setTipo("todos");
            },
          }}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <Ordenavel
                    coluna="nome"
                    atual={coluna}
                    asc={asc}
                    onClick={ordenarPor}
                  >
                    Modelo
                  </Ordenavel>
                  <TableHead>Tipo</TableHead>
                  <Ordenavel
                    coluna="entrada"
                    atual={coluna}
                    asc={asc}
                    onClick={ordenarPor}
                    className="text-right"
                    dica="Quanto custa mandar 1 milhão de tokens para o modelo — as mensagens do cliente, o histórico e as instruções do agente."
                  >
                    Entrada
                  </Ordenavel>
                  <Ordenavel
                    coluna="saida"
                    atual={coluna}
                    asc={asc}
                    onClick={ordenarPor}
                    className="text-right"
                    dica="Quanto custa 1 milhão de tokens gerados pelo modelo — o que o agente responde."
                  >
                    Saída
                  </Ordenavel>
                  <Ordenavel
                    coluna="contexto"
                    atual={coluna}
                    asc={asc}
                    onClick={ordenarPor}
                    className="text-right"
                    dica="Quanto de conversa cabe de uma vez. Passou disso, o histórico mais antigo é cortado."
                  >
                    Contexto
                  </Ordenavel>
                  <TableHead className="text-right">Origem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtrados.map((m) => {
                  const global = m.empresa_id === null;
                  return (
                    <TableRow key={m.id} className={cn(!m.ativo && "opacity-55")}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{m.nome}</p>
                          {!m.ativo && <Badge variant="outline">desligado</Badge>}
                        </div>
                        <p className="font-mono text-xs text-muted-foreground">
                          {m.provedor}/{m.nome}
                        </p>
                        {m.descricao && (
                          <p className="mt-0.5 max-w-md text-xs text-muted-foreground">
                            {m.descricao}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{TIPO_LABEL[m.tipo]}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {preco(m.custo_input_mtok)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {preco(m.custo_output_mtok)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {contexto(m.janela_contexto)}
                      </TableCell>
                      <TableCell className="text-right">
                        {global ? (
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <span className="inline-flex cursor-default items-center gap-1 text-xs text-muted-foreground" />
                              }
                            >
                              <Lock className="size-3" />
                              do catálogo
                            </TooltipTrigger>
                            <TooltipContent>
                              Mantido por nós — disponível pra todas as
                              empresas e não editável aqui.
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          <ButtonLink
                            variant="ghost"
                            size="sm"
                            href={`/catalog/models/${m.id}/edit`}
                          >
                            <Pencil className="size-3.5" />
                            Editar
                          </ButtonLink>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Preços por 1 milhão de tokens, em dólar, como o provedor publica. Um
        token é aproximadamente 4 caracteres.
      </p>
    </div>
  );
}

/** Cabeçalho que ordena, com seta indicando coluna e direção ativas. */
function Ordenavel({
  coluna,
  atual,
  asc,
  onClick,
  children,
  className,
  dica,
}: {
  coluna: Coluna;
  atual: Coluna;
  asc: boolean;
  onClick: (c: Coluna) => void;
  children: React.ReactNode;
  className?: string;
  dica?: string;
}) {
  const ativo = coluna === atual;
  const botao = (
    <button
      type="button"
      onClick={() => onClick(coluna)}
      className={cn(
        "inline-flex items-center gap-1 hover:text-foreground",
        ativo && "text-foreground"
      )}
      aria-label={`Ordenar por ${String(children)}`}
    >
      {children}
      {ativo ? (
        asc ? (
          <ArrowUp className="size-3" />
        ) : (
          <ArrowDown className="size-3" />
        )
      ) : null}
    </button>
  );
  return (
    <TableHead className={className}>
      {dica ? (
        <Tooltip>
          <TooltipTrigger render={<span />}>{botao}</TooltipTrigger>
          <TooltipContent>{dica}</TooltipContent>
        </Tooltip>
      ) : (
        botao
      )}
    </TableHead>
  );
}

/**
 * Preço legível. O de embedding chega a $0.02 e o do Opus a $75 — formato fixo
 * ou some com o primeiro, ou enche o segundo de zero à toa.
 */
function preco(v: number | null): string {
  if (v === null) return "—";
  if (v === 0) return "grátis";
  if (v < 0.1) return `$${v.toFixed(3)}`;
  if (v < 10) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(0)}`;
}

/** 1.048.576 tokens é ilegível; "1M" é o que a pessoa compara. */
function contexto(v: number | null): string {
  if (v === null) return "—";
  if (v >= 1_000_000) {
    const m = v / 1_000_000;
    return `${m >= 10 ? m.toFixed(0) : m.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (v >= 1_000) return `${Math.round(v / 1_000)}k`;
  return String(v);
}
