"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronsDownUp, ChevronsUpDown, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

import { MODOS_AGRUPAMENTO, type ModoAgrupamento } from "./agrupar";

interface Props {
  /** Valor atual de `?q=` — o servidor é quem filtra. */
  q?: string;
  modo: ModoAgrupamento;
  onModo: (m: ModoAgrupamento) => void;
  /** Há algum grupo aberto? Decide o rótulo Expandir/Recolher. */
  algumAberto: boolean;
  onAlternarTodos: () => void;
}

const DEBOUNCE_MS = 400;

/**
 * Barra da lista agrupada: busca, expandir/recolher tudo e "Agrupar por".
 *
 * A busca continua sendo `?q=` (nome, protocolo ou telefone — o backend
 * casa os dígitos), só que sem botão: `debounce` de 400 ms e `router.replace`
 * pra digitar não empilhar histórico. Trocar o `q` re-renderiza a página no
 * servidor (é ele que filtra), então o debounce é o que evita uma ida por
 * tecla. Os outros params (`tipo`, `id`, filtros) são preservados.
 */
export function ListaToolbar({ q, modo, onModo, algumAberto, onAlternarTodos }: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [busca, setBusca] = useState(q ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // O último `q` que ESTA barra empurrou pra URL. Quando o prop volta igual
  // a ele, é o eco da própria digitação e não pode sobrescrever o que o
  // operador já digitou depois (a ida ao servidor demora mais que a tecla).
  const [aplicado, setAplicado] = useState<string | null>(null);

  // A URL mudou por fora (Limpar filtros, voltar do navegador): acompanha.
  // Ajuste de estado durante o render, como manda o React pra "estado que
  // depende de prop" — não num efeito.
  const [ultimoQ, setUltimoQ] = useState(q);
  if (q !== ultimoQ) {
    setUltimoQ(q);
    if ((q ?? "") !== aplicado) setBusca(q ?? "");
  }

  const aplicar = (valor: string) => {
    const limpo = valor.trim();
    if (limpo === (q ?? "")) return;
    setAplicado(limpo);
    const params = new URLSearchParams(sp.toString());
    if (limpo) params.set("q", limpo);
    else params.delete("q");
    router.replace(`/atendimento?${params.toString()}`, { scroll: false });
  };

  const onChange = (valor: string) => {
    setBusca(valor);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => aplicar(valor), DEBOUNCE_MS);
  };

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return (
    <div className="flex flex-col gap-2 border-b p-2">
      <div className="flex items-center gap-2">
        <InputGroup className="h-8 flex-1">
          <InputGroupAddon>
            <Search className="size-3.5" aria-hidden />
          </InputGroupAddon>
          <InputGroupInput
            value={busca}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                if (timer.current) clearTimeout(timer.current);
                aplicar(busca);
              }
            }}
            placeholder="Nome, telefone ou protocolo"
            aria-label="Buscar conversa"
            className="text-xs"
          />
          {busca && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton
                size="icon-xs"
                variant="ghost"
                aria-label="Limpar busca"
                onClick={() => {
                  if (timer.current) clearTimeout(timer.current);
                  setBusca("");
                  aplicar("");
                }}
              >
                <X className="size-3" />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 shrink-0 text-[11px]"
          onClick={onAlternarTodos}
          title={algumAberto ? "Recolher todos os grupos" : "Expandir todos os grupos"}
        >
          {algumAberto ? (
            <ChevronsDownUp className="size-3.5" aria-hidden />
          ) : (
            <ChevronsUpDown className="size-3.5" aria-hidden />
          )}
          {algumAberto ? "Recolher tudo" : "Expandir tudo"}
        </Button>
      </div>

      <div className="flex min-w-0 items-center gap-2">
        {/* Some quando a lista está estreita (container query da coluna):
            a 320px os três botões não cabem ao lado do rótulo. */}
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground @max-[400px]:sr-only">
          Agrupar por
        </span>
        <div
          role="radiogroup"
          aria-label="Agrupar por"
          className="flex min-w-0 flex-1 gap-0.5 rounded-lg bg-muted p-0.5"
        >
          {MODOS_AGRUPAMENTO.map((m) => {
            const ativo = m.valor === modo;
            return (
              <Button
                key={m.valor}
                type="button"
                role="radio"
                aria-checked={ativo}
                size="xs"
                variant="ghost"
                onClick={() => onModo(m.valor)}
                className={cn(
                  "h-6 min-w-0 flex-1 px-1 text-[11px]",
                  ativo
                    ? "bg-background text-foreground shadow-sm hover:bg-background"
                    : "text-muted-foreground"
                )}
              >
                {m.rotulo}
              </Button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
