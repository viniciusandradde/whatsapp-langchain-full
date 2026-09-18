"use client";

import { GripVertical } from "lucide-react";

import type { useColunaRedimensionavel } from "@/hooks/use-colunas-redimensionaveis";
import { cn } from "@/lib/utils";

type AlcaProps = ReturnType<typeof useColunaRedimensionavel>["alcaProps"];

interface Props {
  alcaProps: AlcaProps;
  /** Breakpoint em que a alça aparece (o rail existe a partir de `md`, a
   *  divisão lista/conversa a partir de `lg`). */
  className?: string;
}

/**
 * Alça entre duas colunas (inbox agrupado 2026-09): faixa de 12px com uma
 * linha e um pegador no meio, que acende no hover. A 1ª versão era só a
 * linha de 1px — o dono olhou a captura e achou que não dava pra
 * redimensionar. Alça que não se anuncia não existe.
 */
export function AlcaColuna({ alcaProps, className }: Props) {
  return (
    <div
      {...alcaProps}
      title="Arraste para redimensionar · duplo clique redefine"
      className={cn(
        "group/alca relative hidden w-3 shrink-0 cursor-col-resize select-none lg:block",
        className
      )}
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover/alca:w-0.5 group-hover/alca:bg-brand-primary/70" />
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-md border bg-background py-1 text-muted-foreground shadow-sm transition-colors group-hover/alca:border-brand-primary/50 group-hover/alca:text-brand-primary">
        <GripVertical className="size-3" aria-hidden />
      </div>
    </div>
  );
}
