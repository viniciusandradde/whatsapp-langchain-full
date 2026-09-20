"use client";

import {
  ArrowLeft,
  ArrowRightLeft,
  Bot,
  CheckCircle2,
  Eraser,
  FileText,
  FolderOpen,
  Hand,
  Info,
  MoreVertical,
  RefreshCw,
  ShieldOff,
  Tag as TagIcon,
  X,
  XCircle,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Atendimento } from "@/lib/api";
import { cn } from "@/lib/utils";

import { ITENS_TOQUE } from "./composer-menu";
import { iniciaisDe, type SecaoInfo } from "./info-conversa";
import { SITUACAO_AJUDA, SITUACAO_CHIP, SITUACAO_LABEL, SITUACAO_PONTO } from "./situacao";

export interface AcoesCabecalho {
  onAtender: () => void;
  onDevolverParaIa: () => void;
  onTransferir: () => void;
  onResolver: () => void;
  onAbandonar: () => void;
  onInserirModelo: () => void;
  onAtualizar: () => void;
  onResetarConversa: () => void;
  /** Ausente quando o usuário não tem `whitelist.manage` ou não há telefone. */
  onIncluirSemIa?: () => void;
}

/**
 * Cabeçalho compacto da conversa (conversa compacta, 2026-09):
 *
 *   ←  avatar  Nome ● situação            [Ação principal]  ⋮
 *              telefone · setor
 *
 * Só o que decide o próximo toque fica visível. O resto (protocolo, id,
 * tags, badges, ficha, arquivos, triagem, histórico) abre a um toque no
 * avatar/nome ou no ⋮ — nada foi removido, saiu da área permanente.
 *
 * A ação principal depende do estado: aguardando → Atender; em andamento →
 * Resolver. Transferir, Devolver à IA, Abandonar e o resto ficam no ⋮.
 */
export function CabecalhoConversa({
  atendimento,
  departamentoNome,
  modo,
  pendente,
  infoAberta,
  onVoltar,
  onAbrirInfo,
  acoes,
}: {
  atendimento: Atendimento;
  departamentoNome?: string | null;
  modo: "drawer" | "painel";
  pendente: boolean;
  infoAberta: boolean;
  onVoltar: () => void;
  onAbrirInfo: (secao?: SecaoInfo) => void;
  acoes: AcoesCabecalho;
}) {
  const a = atendimento;
  const aberto = a.status === "aguardando" || a.status === "em_andamento";
  const nome = a.cliente_nome ?? a.cliente_telefone ?? "Cliente";
  const linha2 = [a.cliente_telefone, departamentoNome ?? a.agente_atual].filter(Boolean).join(" · ");
  const Voltar = modo === "drawer" ? ArrowLeft : X;

  return (
    <header className="flex shrink-0 items-center gap-1 border-b bg-card px-1.5 py-1.5 sm:gap-2 sm:px-2">
      <Button
        variant="ghost"
        size="icon"
        onClick={onVoltar}
        aria-label={modo === "drawer" ? "Voltar para a fila" : "Fechar conversa"}
        className="shrink-0"
      >
        <Voltar className="size-4" />
      </Button>

      <button
        type="button"
        onClick={() => onAbrirInfo("contato")}
        aria-pressed={infoAberta}
        aria-label={`Informações de ${nome}`}
        title="Informações do contato"
        className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/60"
      >
        <Avatar>
          <AvatarFallback className="text-xs font-medium">{iniciaisDe(a.cliente_nome)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          {/* O nome tem prioridade: não encolhe até 60% da linha; o chip da
              situação fica com a sobra e trunca ("Aguardando h…"). Com os
              dois encolhendo, "Medição 7" virava "Me…" no celular. */}
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="max-w-[60%] shrink-0 truncate text-sm font-semibold leading-tight">
              {nome}
            </span>
            <span
              className={cn(
                "inline-flex min-w-0 items-center gap-1 rounded-full px-1.5 py-px text-[10px] font-medium",
                SITUACAO_CHIP[a.situacao]
              )}
              title={SITUACAO_AJUDA[a.situacao]}
            >
              <span
                className={cn("size-1.5 shrink-0 rounded-full", SITUACAO_PONTO[a.situacao])}
                aria-hidden
              />
              <span className="truncate">{SITUACAO_LABEL[a.situacao]}</span>
            </span>
          </div>
          <p className="truncate font-mono text-[10px] leading-tight text-muted-foreground">
            {linha2 || "—"}
          </p>
        </div>
      </button>

      {aberto && a.status === "aguardando" && (
        <Button size="sm" onClick={acoes.onAtender} disabled={pendente} className="shrink-0">
          <Hand className="size-3.5" />
          Atender
        </Button>
      )}
      {aberto && a.status === "em_andamento" && (
        <Button size="sm" onClick={acoes.onResolver} disabled={pendente} className="shrink-0">
          <CheckCircle2 className="size-3.5" />
          Resolver
        </Button>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant="ghost" size="icon" aria-label="Mais ações" className="shrink-0" />}
        >
          <MoreVertical className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className={cn("min-w-56", ITENS_TOQUE)}>
          <DropdownMenuGroup>
            <DropdownMenuLabel>Contato</DropdownMenuLabel>
            <DropdownMenuItem onClick={() => onAbrirInfo("contato")}>
              <Info /> Informações e histórico
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onAbrirInfo("contato")}>
              <TagIcon /> Tags
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onAbrirInfo("arquivos")}>
              <FolderOpen /> Arquivos
            </DropdownMenuItem>
          </DropdownMenuGroup>

          {aberto && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel>Atendimento</DropdownMenuLabel>
                {a.status === "em_andamento" && (
                  <DropdownMenuItem onClick={acoes.onDevolverParaIa} disabled={pendente}>
                    <Bot /> Devolver para a IA
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={acoes.onTransferir} disabled={pendente}>
                  <ArrowRightLeft /> Transferir
                </DropdownMenuItem>
                {a.status === "aguardando" && (
                  <DropdownMenuItem onClick={acoes.onResolver} disabled={pendente}>
                    <CheckCircle2 /> Resolver
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={acoes.onAbandonar} disabled={pendente} variant="destructive">
                  <XCircle /> Abandonar
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            {aberto && (
              <DropdownMenuItem onClick={acoes.onInserirModelo}>
                <FileText /> Inserir modelo de mensagem
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={acoes.onAtualizar}>
              <RefreshCw /> Atualizar conversa
            </DropdownMenuItem>
          </DropdownMenuGroup>

          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel>Avançado</DropdownMenuLabel>
            {acoes.onIncluirSemIa && (
              <DropdownMenuItem onClick={acoes.onIncluirSemIa}>
                <ShieldOff /> Incluir em números sem IA
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={acoes.onResetarConversa}>
              <Eraser /> Resetar conversa do agente
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
