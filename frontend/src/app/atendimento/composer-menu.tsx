"use client";

import { FileText, Lock, MessageSquareText, Paperclip, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Itens com 40px de altura no toque (sem ponteiro fino); 28px no desktop. */
export const ITENS_TOQUE =
  "[&_[role^=menuitem]]:py-2.5 [@media(pointer:fine)]:[&_[role^=menuitem]]:py-1";

/**
 * Menu `+` do composer compacto (2026-09): o que antes ocupava uma linha
 * própria acima do campo (checkbox "Nota interna" + "Template") e o clipe
 * moram aqui. O microfone continua ao lado do campo — gravar é o gesto mais
 * frequente depois de digitar.
 */
export function ComposerMenu({
  disabled,
  notaInterna,
  onAnexar,
  onTemplate,
  onNotaInterna,
  onModelo,
}: {
  disabled?: boolean;
  notaInterna: boolean;
  onAnexar: () => void;
  onTemplate: () => void;
  onNotaInterna: (ativa: boolean) => void;
  onModelo: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={disabled}
            aria-label="Mais opções de envio"
            title="Anexo, template, nota interna, modelo"
            className="shrink-0"
          />
        }
      >
        <Plus className="size-5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className={cn("min-w-52", ITENS_TOQUE)}>
        <DropdownMenuItem onClick={onAnexar} disabled={notaInterna}>
          <Paperclip /> Anexar arquivo
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onTemplate} disabled={notaInterna}>
          <FileText /> Enviar template
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onModelo}>
          <MessageSquareText /> Inserir modelo
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">/</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuCheckboxItem
          checked={notaInterna}
          closeOnClick
          onCheckedChange={(v) => onNotaInterna(Boolean(v))}
        >
          <Lock /> Nota interna
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
