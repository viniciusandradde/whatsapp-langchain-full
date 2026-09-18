"use client";

import { Clock, Frown, Mail, MessageCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Atendimento } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  FAIXA_ESPERA_CLASSE,
  PRIORIDADE_PONTO,
  SITUACAO_AJUDA,
  SITUACAO_CHIP,
  SITUACAO_LABEL,
  faixaEspera,
  formatarEspera,
  formatarNaoLidas,
} from "./situacao";

export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h`;
  const d = Math.round(h / 24);
  return `${d}d`;
}

/** "+5567999791234" → "+55 67 99979-1234"; outro formato volta como veio. */
export function formatarTelefone(tel: string | null): string | null {
  if (!tel) return null;
  const m = /^\+?55(\d{2})(\d{4,5})(\d{4})$/.exec(tel);
  return m ? `+55 ${m[1]} ${m[2]}-${m[3]}` : tel;
}

interface Props {
  atendimento: Atendimento;
  selecionado: boolean;
  departamentoNome?: string | null;
  onSelecionar: (a: Atendimento) => void;
  onMarcarNaoLida: (id: number) => void;
}

/**
 * Card da fila agrupada (inbox agrupado 2026-09).
 *
 * Linha 1: canal, nome, tempo da última mensagem. Linha 2 (mono): telefone ·
 * departamento. Prévia. Chips: automação, "Sem resposta há X" (só quando o
 * cliente falou por último — `aguardando_desde` do backend), não lidas,
 * prioridade e sentimento; até 3 tags do cliente.
 *
 * Os tempos ("há 12min", "Sem resposta há 3h") leem o relógio nos helpers;
 * a lista re-renderiza a cada minuto (tick em `atendimento-list.tsx`) e este
 * card, sem memo, acompanha.
 *
 * A ação "marcar não lida" é IRMÃ do botão do card, não filha: button dentro
 * de button é HTML inválido e o clique selecionaria a conversa.
 */
export function CardAtendimento({
  atendimento: a,
  selecionado,
  departamentoNome,
  onSelecionar,
  onMarcarNaoLida,
}: Props) {
  const telefone = formatarTelefone(a.cliente_telefone);
  const faixa = a.aguardando_desde ? faixaEspera(a.aguardando_desde) : null;

  return (
    <li className="group/card relative">
      <button
        type="button"
        onClick={() => onSelecionar(a)}
        aria-current={selecionado ? "true" : undefined}
        className={cn(
          "flex w-full flex-col gap-1 border-l-2 px-3 py-2.5 text-left transition-colors",
          selecionado
            ? "border-l-brand-primary bg-accent"
            : "border-l-transparent hover:bg-accent/50"
        )}
      >
        <div className="flex items-center gap-2">
          <MessageCircle
            className="size-3.5 shrink-0 text-success"
            aria-label="WhatsApp"
          />
          <span className="truncate text-sm font-medium">
            {a.cliente_nome ?? telefone ?? "Cliente"}
          </span>
          <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
            {formatRelative(a.last_message_at)}
          </span>
        </div>

        <div className="flex min-w-0 items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
          {telefone && <span className="shrink-0">{telefone}</span>}
          {telefone && departamentoNome && <span aria-hidden>·</span>}
          {departamentoNome && <span className="truncate">{departamentoNome}</span>}
        </div>

        {a.ultima_mensagem_preview && (
          <p className="truncate text-xs text-muted-foreground">
            {a.ultima_mensagem_preview}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              "inline-flex h-5 items-center rounded-md px-1.5 text-[10px] font-medium",
              SITUACAO_CHIP[a.situacao]
            )}
            title={SITUACAO_AJUDA[a.situacao]}
          >
            {SITUACAO_LABEL[a.situacao]}
          </span>
          {a.aguardando_desde && faixa && (
            <span
              className={cn(
                "inline-flex h-5 items-center gap-1 rounded-md px-1.5 font-mono text-[10px]",
                FAIXA_ESPERA_CLASSE[faixa]
              )}
              title={`Cliente sem resposta desde ${new Date(a.aguardando_desde).toLocaleString("pt-BR")}`}
            >
              <Clock className="size-3" aria-hidden />
              Sem resposta há {formatarEspera(a.aguardando_desde)}
            </span>
          )}
          {a.nao_lidas > 0 && (
            <span
              className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[10px] font-bold text-destructive-foreground"
              title={`${a.nao_lidas} nova(s) do cliente`}
            >
              {formatarNaoLidas(a.nao_lidas)}
            </span>
          )}
          {a.prioridade && PRIORIDADE_PONTO[a.prioridade] && (
            <span
              className={cn("size-2 shrink-0 rounded-full", PRIORIDADE_PONTO[a.prioridade])}
              title={`Prioridade ${a.prioridade}`}
            />
          )}
          {(a.sentimento === "negativo" || a.sentimento === "frustrado") && (
            <span
              className="shrink-0"
              title={`Cliente ${a.sentimento}${a.resumo_ia ? ` — ${a.resumo_ia.slice(0, 120)}` : ""}`}
            >
              <Frown className="size-3 text-destructive" aria-label={`Cliente ${a.sentimento}`} />
            </span>
          )}
        </div>

        {a.cliente_tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {a.cliente_tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="outline" className="h-4 px-1 text-[10px]">
                {tag}
              </Badge>
            ))}
            {a.cliente_tags.length > 3 && (
              <span className="text-[10px] text-muted-foreground">
                +{a.cliente_tags.length - 3}
              </span>
            )}
          </div>
        )}
      </button>
      {a.nao_lidas === 0 && (
        <button
          type="button"
          onClick={() => onMarcarNaoLida(a.id)}
          aria-label="Marcar como não lida"
          title="Marcar como não lida (abrir a conversa marca como lida de novo)"
          className="absolute bottom-1.5 right-1.5 rounded-md border bg-background p-1 text-muted-foreground opacity-0 shadow-sm transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover/card:opacity-100"
        >
          <Mail className="size-3.5" />
        </button>
      )}
    </li>
  );
}
