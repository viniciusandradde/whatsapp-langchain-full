"use client";

import { Info } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/**
 * Ícone de ajuda ao lado do rótulo de um campo de formulário (pedido do dono,
 * 2026-08-28: "cada item deve explicar detalhadamente como e para que serve").
 *
 * Popover (clique/toque), não Tooltip: o painel é usado no CELULAR — hover não
 * existe lá, e foi numa captura mobile que o pedido nasceu. `type="button"`
 * é load-bearing: os campos vivem dentro do <form> do editor e um botão sem
 * tipo submeteria o form ao abrir a ajuda.
 */
export function AjudaCampo({ titulo, children }: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={`Ajuda: ${titulo}`}
            className="inline-flex text-muted-foreground transition-colors hover:text-foreground"
          />
        }
      >
        <Info className="size-3.5" />
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="max-w-80">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {titulo}
        </p>
        <div className="space-y-1.5 text-sm leading-relaxed [&_b]:font-medium">
          {children}
        </div>
      </PopoverContent>
    </Popover>
  );
}
