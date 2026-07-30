"use client";

import { useState } from "react";
import { Headphones } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Atendimento, TipoVisualizacao } from "@/lib/api";
import { cn } from "@/lib/utils";

import { AtendimentoDrawer } from "./atendimento-drawer";
import {
  SITUACAO_AJUDA,
  SITUACAO_CLASSE,
  SITUACAO_LABEL,
  formatarNaoLidas,
} from "./situacao";

interface Props {
  atendimentos: Atendimento[];
  tipo: TipoVisualizacao;
}

const PRIORIDADE_CLASSE: Record<string, string> = {
  urgente: "border-destructive/40 bg-destructive/10 text-destructive",
  alta: "border-warning/40 bg-warning/10 text-warning",
  media: "border-border bg-muted text-muted-foreground",
  baixa: "border-border bg-muted text-muted-foreground",
};

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
export function AtendimentoList({ atendimentos, tipo }: Props) {
  const [ativo, setAtivo] = useState<Atendimento | null>(null);

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
      <div className="flex w-full min-w-0 flex-col overflow-hidden rounded-lg border lg:w-[380px] lg:shrink-0">
        <ul className="divide-y overflow-y-auto">
          {atendimentos.map((a) => {
            const selecionado = ativo?.id === a.id;
            return (
              <li key={a.id}>
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
                        "inline-flex items-center rounded border px-1.5 py-px text-[10px] font-medium",
                        SITUACAO_CLASSE[a.situacao]
                      )}
                      title={SITUACAO_AJUDA[a.situacao]}
                    >
                      {SITUACAO_LABEL[a.situacao]}
                    </span>
                    {a.prioridade && a.prioridade !== "media" && (
                      <span
                        className={cn(
                          "inline-flex items-center rounded border px-1.5 py-px text-[10px] font-medium",
                          PRIORIDADE_CLASSE[a.prioridade]
                        )}
                      >
                        {a.prioridade}
                      </span>
                    )}
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                      #{a.id}
                    </span>
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
