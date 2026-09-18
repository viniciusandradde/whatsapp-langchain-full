"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Frown, Headphones, Mail } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import type { Atendimento, TipoVisualizacao } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  carregarAtendimentosAction,
  marcarAtendimentoNaoLidoAction,
  type FiltrosFila,
} from "./actions";
import { AtendimentoDrawer } from "./atendimento-drawer";
import {
  PRIORIDADE_PONTO,
  SITUACAO_AJUDA,
  SITUACAO_LABEL,
  SITUACAO_PONTO,
  formatarNaoLidas,
} from "./situacao";

interface Props {
  /** Render do servidor — vira `initialData` do Query (sem flash, sem refetch
   *  no mount). A partir daí quem manda na lista é o cache. */
  atendimentos: Atendimento[];
  tipo: TipoVisualizacao;
  /** Compõe a queryKey: trocar de filtro é outra chave, outro initialData. */
  filtros: FiltrosFila;
}

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h`;
  const d = Math.round(h / 24);
  return `${d}d`;
}

/**
 * Fila + conversa, lado a lado.
 *
 * Antes: grade de cards de ~250px de altura, e a conversa abria num drawer
 * sobre backdrop escuro — o operador via a fila OU lia a conversa, nunca as
 * duas. Com 77 atendimentos abertos isso é rolagem o dia inteiro.
 *
 * Agora a fila é uma coluna densa de linhas e a conversa ocupa a coluna da
 * direita. Abaixo de `lg` (tablet/celular) o drawer continua, porque 390px não
 * comportam duas colunas.
 */
export function AtendimentoList({
  atendimentos: iniciais,
  tipo,
  filtros,
}: Props) {
  const [ativo, setAtivo] = useState<Atendimento | null>(null);
  const queryClient = useQueryClient();

  // A fila passa a ser servida pelo cache do Query: o evento SSE invalida a
  // chave e SÓ esta lista revalida — antes, `router.refresh()` refazia os
  // quatro fetches da página inteira a cada mensagem.
  const { data: atendimentos } = useQuery({
    queryKey: ["atendimentos", filtros],
    queryFn: async () => {
      const r = await carregarAtendimentosAction(filtros);
      // Lançar (em vez de devolver o erro) é o que liga o retry/backoff do
      // Query — inclusive o recuo no 429.
      if (!r.ok) throw new Error(r.error);
      return r.atendimentos;
    },
    initialData: iniciais,
  });

  async function marcarNaoLida(atendimentoId: number) {
    const r = await marcarAtendimentoNaoLidoAction(atendimentoId);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    // O badge vem calculado no servidor — revalida só a fila.
    queryClient.invalidateQueries({ queryKey: ["atendimentos"] });
  }

  if (atendimentos.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        <p className="font-medium">Nenhum atendimento nessa caixa</p>
        <p className="mt-1 text-sm">
          {tipo === "grupos"
            ? "Atendimentos de grupos serão habilitados em uma versão futura."
            : "Quando uma mensagem nova chegar, ela aparece aqui automaticamente."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 gap-4">
      <div className="flex w-full min-w-0 flex-col overflow-hidden rounded-lg border lg:w-[300px] lg:shrink-0">
        <ul className="divide-y overflow-y-auto">
          {atendimentos.map((a) => {
            const selecionado = ativo?.id === a.id;
            return (
              // group/card + irmão absoluto: a ação de não-lida NÃO pode
              // ficar DENTRO do botão da linha (button aninhado é HTML
              // inválido e o clique selecionaria a conversa).
              <li key={a.id} className="group/card relative">
                <button
                  type="button"
                  onClick={() => setAtivo(a)}
                  aria-current={selecionado ? "true" : undefined}
                  className={cn(
                    "w-full px-3 py-2.5 text-left transition-colors",
                    selecionado
                      ? "bg-accent"
                      : "hover:bg-accent/50"
                  )}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium">
                      {a.cliente_nome ?? a.cliente_telefone ?? "Cliente"}
                    </span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {formatRelative(a.last_message_at)}
                    </span>
                  </div>

                  {a.ultima_mensagem_preview && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {a.ultima_mensagem_preview}
                    </p>
                  )}

                  {/* Linha compacta: badges viraram pontos com tooltip pra
                      caber nos 300px — o rótulo inteiro vive no `title`. O
                      #id saiu: o protocolo já identifica no header do drawer. */}
                  <div className="mt-1 flex items-center gap-1.5">
                    {a.nao_lidas > 0 && (
                      <span
                        className="inline-flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold leading-4 text-destructive-foreground"
                        title={`${a.nao_lidas} nova(s) do cliente`}
                      >
                        {formatarNaoLidas(a.nao_lidas)}
                      </span>
                    )}
                    <span
                      className={cn(
                        "size-2 shrink-0 rounded-full",
                        SITUACAO_PONTO[a.situacao]
                      )}
                      title={`${SITUACAO_LABEL[a.situacao]} — ${SITUACAO_AJUDA[a.situacao]}`}
                    />
                    <span className="truncate text-[10px] text-muted-foreground">
                      {SITUACAO_LABEL[a.situacao]}
                    </span>
                    {a.prioridade && PRIORIDADE_PONTO[a.prioridade] && (
                      <span
                        className={cn(
                          "size-2 shrink-0 rounded-full",
                          PRIORIDADE_PONTO[a.prioridade]
                        )}
                        title={`Prioridade ${a.prioridade}`}
                      />
                    )}
                    {(a.sentimento === "negativo" ||
                      a.sentimento === "frustrado") && (
                      <span
                        className="ml-auto shrink-0"
                        title={`Cliente ${a.sentimento}${a.resumo_ia ? ` — ${a.resumo_ia.slice(0, 120)}` : ""}`}
                      >
                        <Frown
                          className="size-3 text-destructive"
                          aria-label={`Cliente ${a.sentimento}`}
                        />
                      </span>
                    )}
                  </div>

                  {a.cliente_tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
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
                    onClick={() => void marcarNaoLida(a.id)}
                    aria-label="Marcar como não lida"
                    title="Marcar como não lida (abrir a conversa marca como lida de novo)"
                    className="absolute bottom-1.5 right-1.5 rounded-md border bg-background p-1 text-muted-foreground opacity-0 shadow-sm transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover/card:opacity-100"
                  >
                    <Mail className="size-3.5" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {/* Coluna da conversa — só desktop. */}
      <div className="hidden min-w-0 flex-1 overflow-hidden rounded-lg border lg:flex">
        {ativo ? (
          <AtendimentoDrawer
            key={ativo.id}
            atendimento={ativo}
            onClose={() => setAtivo(null)}
            modo="painel"
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center text-muted-foreground">
            <Headphones className="size-8 opacity-40" />
            <p className="text-sm">Escolha uma conversa na fila ao lado.</p>
          </div>
        )}
      </div>

      {/* Mobile mantém o overlay. */}
      {ativo && (
        <div className="lg:hidden">
          <AtendimentoDrawer
            atendimento={ativo}
            onClose={() => setAtivo(null)}
          />
        </div>
      )}
    </div>
  );
}
