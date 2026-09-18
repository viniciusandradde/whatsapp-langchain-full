"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

import type { Grupo } from "./agrupar";
import { formatarNaoLidas } from "./situacao";

interface Props {
  grupo: Grupo;
  aberto: boolean;
  onAlternar: (id: string) => void;
  children: React.ReactNode;
}

/**
 * Um grupo da fila: cabeçalho fixo no topo da rolagem + cards quando aberto.
 *
 * O cabeçalho é `sticky` DENTRO do container que rola (a `<ul>` da lista), e
 * cada grupo é um `<li>` — o sticky de um grupo só vale enquanto o grupo
 * está na tela, então os cabeçalhos se revezam conforme a rolagem, como
 * seções de uma lista de contatos.
 */
export function GrupoFila({ grupo, aberto, onAlternar, children }: Props) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onAlternar(grupo.id)}
        aria-expanded={aberto}
        title={grupo.ajuda}
        className="sticky top-0 z-10 flex w-full items-center gap-2 border-b bg-background/95 px-3 py-2 text-left backdrop-blur transition-colors hover:bg-accent/50"
      >
        <ChevronDown
          className={cn(
            "size-3 shrink-0 text-muted-foreground transition-transform",
            !aberto && "-rotate-90"
          )}
          aria-hidden
        />
        <span className={cn("size-2 shrink-0 rounded-full", grupo.ponto)} aria-hidden />
        <span className="truncate font-mono text-[10px] font-medium uppercase tracking-[.14em]">
          {grupo.nome}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">{grupo.itens.length}</span>
        {grupo.naoLidas > 0 && (
          <span
            className="ml-auto inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground"
            title={`${grupo.naoLidas} mensagem(ns) não lida(s) neste grupo`}
          >
            {formatarNaoLidas(grupo.naoLidas)}
          </span>
        )}
      </button>
      {aberto && <ul className="divide-y">{children}</ul>}
    </li>
  );
}
