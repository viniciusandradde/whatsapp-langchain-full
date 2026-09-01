"use client";

import { useEffect, useRef } from "react";
import { FileText } from "lucide-react";

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import type { ModeloMensagem } from "@/lib/api";

/**
 * Busca rápida de modelos de mensagem, aberta pelo "/" no composer vazio
 * (leva fila 2026-08). Os modelos existiam mas custavam dois cliques num
 * kebab — atalho enterrado é feature morta.
 *
 * Painel ancorado acima do composer (o container do composer é `relative`),
 * não um Dialog: o operador está digitando e o foco volta pro textarea ao
 * escolher. O cmdk filtra por título, atalho e conteúdo via `value`.
 */
export function ModelosPopover({
  modelos,
  onEscolher,
  onFechar,
}: {
  modelos: ModeloMensagem[] | null;
  onEscolher: (m: ModeloMensagem) => void;
  onFechar: () => void;
}) {
  const raiz = useRef<HTMLDivElement | null>(null);

  // Clique fora fecha — listener no document, sem overlay à mão (métrica).
  useEffect(() => {
    function aoClicarFora(e: MouseEvent) {
      if (raiz.current && !raiz.current.contains(e.target as Node)) onFechar();
    }
    document.addEventListener("mousedown", aoClicarFora);
    return () => document.removeEventListener("mousedown", aoClicarFora);
  }, [onFechar]);

  return (
    <div
      ref={raiz}
      className="absolute bottom-full left-3 right-3 z-30 mb-1 overflow-hidden rounded-md border bg-popover shadow-lg"
    >
      <Command>
        <CommandInput
          autoFocus
          placeholder="Buscar modelo de mensagem…"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onFechar();
            }
          }}
        />
        <CommandList className="max-h-56">
          <CommandEmpty>
            {modelos === null
              ? "Carregando modelos…"
              : "Nenhum modelo encontrado. Crie em Modelos de mensagem."}
          </CommandEmpty>
          {(modelos ?? []).map((m) => (
            <CommandItem
              key={m.id}
              value={`${m.titulo} ${m.atalho ?? ""} ${m.conteudo}`}
              onSelect={() => onEscolher(m)}
            >
              <FileText />
              <span className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{m.titulo}</span>
                <span className="line-clamp-1 text-xs text-muted-foreground">
                  {m.conteudo}
                </span>
              </span>
            </CommandItem>
          ))}
        </CommandList>
      </Command>
    </div>
  );
}
