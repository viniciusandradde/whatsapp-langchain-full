"use client";

import { Bot, ChevronRight, X } from "lucide-react";

import type { Atendimento } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useCollapseState } from "./info-conversa";
import { PRIORIDADE_CHIP, SENTIMENTO_CHIP, primeiraLinhaDoResumo } from "./situacao";

/**
 * Faixa de triagem da IA — uma linha logo abaixo do cabeçalho, só quando o
 * agente classificou a conversa:
 *
 *   🤖 alta · frustrado · suporte_tecnico_latencia · Cliente relata latência…  ›
 *
 * É o contexto que o operador precisa ANTES de responder (tom e assunto),
 * por isso não foi pro painel junto com o resto: ficou visível, mas em
 * ~28px em vez do card de antes. Tocar abre o painel na seção da triagem,
 * com o resumo inteiro; o ✕ esconde a faixa nesta conversa (lembrado por
 * atendimento) — ela volta pelo link no painel.
 */
export function FaixaTriagem({
  atendimento,
  onAbrir,
}: {
  atendimento: Atendimento;
  onAbrir: () => void;
}) {
  const a = atendimento;
  const [oculta, setOculta] = useCollapseState(`triagem-faixa-${a.id}`, false);
  const resumo = primeiraLinhaDoResumo(a.resumo_ia);
  const tem = a.prioridade || a.sentimento || a.classificacao || resumo;
  if (!tem || oculta) return null;

  return (
    <div className="flex shrink-0 items-center gap-1 border-b bg-muted/30 px-1.5 py-1 text-[11px] sm:px-2">
      <button
        type="button"
        onClick={onAbrir}
        title="Ver a triagem completa"
        aria-label="Ver a triagem da IA"
        className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/60"
      >
        <Bot className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        {a.prioridade && (
          <span
            className={cn(
              "shrink-0 rounded px-1.5 py-px font-medium",
              PRIORIDADE_CHIP[a.prioridade] ?? "bg-muted text-muted-foreground"
            )}
            title={`Prioridade: ${a.prioridade}`}
          >
            {a.prioridade}
          </span>
        )}
        {a.sentimento && (
          <span
            className={cn(
              "shrink-0 rounded px-1.5 py-px font-medium",
              SENTIMENTO_CHIP[a.sentimento] ?? "bg-muted text-muted-foreground"
            )}
            title={`Sentimento: ${a.sentimento}`}
          >
            {a.sentimento}
          </span>
        )}
        {a.classificacao && (
          <span className="hidden max-w-[35%] shrink truncate font-mono text-muted-foreground sm:inline">
            {a.classificacao}
          </span>
        )}
        {resumo && <span className="min-w-0 flex-1 truncate text-foreground/80">{resumo}</span>}
        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      </button>
      <button
        type="button"
        onClick={() => setOculta(true)}
        aria-label="Esconder a faixa de triagem nesta conversa"
        title="Esconder (volta pelo painel de informações)"
        className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
