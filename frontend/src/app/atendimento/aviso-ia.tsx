"use client";

import { Bot, TriangleAlert } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

import { BotaoReprocessar } from "./grupo-mensagens";
import { AVISO_IA_TEXTO, type AvisoIa as AvisoIaItem } from "./timeline";

/**
 * Aviso compacto da IA na timeline (conversa compacta, 2026-09).
 *
 * Antes cada mensagem pulada pelo worker vinha com uma linha inteira
 * "NÚMERO NA LISTA DE BLOQUEIO DA IA — NINGUÉM RESPONDEU" e o próprio botão
 * de reprocesso. Agora é UM chip por sequência de mensagens com o mesmo
 * motivo; tocar abre o motivo completo e o "Reprocessar com IA" de cada
 * mensagem coberta (o backend revalida os gates a cada clique).
 *
 * `handoff` não vira chip: o cabeçalho já diz "Em atendimento" e o grupo da
 * resposta diz "Operador" — repetir "operador respondendo" depois de cada
 * fala do cliente é o ruído que esta leva tira.
 */
export function AvisoIa({
  aviso,
  atendimentoId,
  onReprocessado,
}: {
  aviso: AvisoIaItem;
  atendimentoId: number;
  onReprocessado: () => void;
}) {
  if (aviso.variante === "handoff") return null;
  const texto = AVISO_IA_TEXTO[aviso.variante];
  const bloqueio = aviso.variante !== "fila";
  const Icone = bloqueio ? TriangleAlert : Bot;

  return (
    <div className="flex justify-center py-0.5">
      <Popover>
        <PopoverTrigger
          render={
            <button
              type="button"
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium transition-colors",
                bloqueio
                  ? "border-warning/40 bg-warning/10 text-warning hover:bg-warning/20"
                  : "border-brand-primary/30 bg-brand-primary/10 text-brand-primary hover:bg-brand-primary/20"
              )}
            />
          }
        >
          <Icone className="size-3.5" aria-hidden />
          {texto.chip}
          {aviso.mensagens.length > 1 && (
            <span className="font-mono opacity-70">· {aviso.mensagens.length}</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-80 max-w-[calc(100vw-2rem)]">
          <PopoverHeader>
            <PopoverTitle className="flex items-center gap-1.5">
              <Icone className="size-4" aria-hidden />
              {texto.titulo}
            </PopoverTitle>
            <PopoverDescription>{texto.motivo}</PopoverDescription>
          </PopoverHeader>
          {aviso.podeReprocessar && (
            <ul className="max-h-56 space-y-1.5 overflow-y-auto">
              {aviso.mensagens.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between gap-2 rounded-md bg-muted/50 px-2 py-1.5"
                >
                  <span className="min-w-0 flex-1 truncate text-xs" title={m.incoming_message}>
                    {m.incoming_message || (m.media_type ? `📎 ${m.media_type}` : "—")}
                  </span>
                  <BotaoReprocessar
                    atendimentoId={atendimentoId}
                    messageId={m.id}
                    onReprocessado={onReprocessado}
                    compacto
                  />
                </li>
              ))}
            </ul>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
