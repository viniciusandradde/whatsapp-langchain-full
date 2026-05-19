"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  History,
  Loader2,
  PauseCircle,
  Phone,
  User as UserIcon,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Atendimento } from "@/lib/api";

import { loadClienteHistoricoAction } from "./actions";

type StatusKey = "aguardando" | "em_andamento" | "resolvido" | "abandonado";

const STATUS_META: Record<
  StatusKey,
  { label: string; cls: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  aguardando: {
    label: "Aguardando",
    cls: "text-amber-600 dark:text-amber-400",
    Icon: Clock,
  },
  em_andamento: {
    label: "Em andamento",
    cls: "text-blue-600 dark:text-blue-400",
    Icon: PauseCircle,
  },
  resolvido: {
    label: "Resolvido",
    cls: "text-green-600 dark:text-green-400",
    Icon: CheckCircle2,
  },
  abandonado: {
    label: "Abandonado",
    cls: "text-muted-foreground",
    Icon: XCircle,
  },
};

interface Props {
  atendimentoId: number;
  clienteId: number | null;
  clienteNome: string | null;
  clienteTelefone: string | null;
}

/**
 * Painel persistente de contexto do cliente — 3a coluna do drawer.
 * Mostra info essencial + histórico de atendimentos anteriores. Foi
 * pensado pro atendente humano ter contexto sem precisar abrir ficha
 * em outra aba.
 *
 * Em desktop (lg+): coluna colapsável à direita
 * Em mobile (<lg): bloco abaixo da timeline (sempre expandido)
 */
export function PainelCliente({
  atendimentoId,
  clienteId,
  clienteNome,
  clienteTelefone,
}: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [historico, setHistorico] = useState<Atendimento[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Carrega só o último atendimento anterior — quem precisa ver
  // histórico completo abre a ficha do cliente via "Ver ficha completa".
  // Trade-off: 1 req leve no abrir vs N reqs ao listar 10 (que ainda
  // ninguém olha caso a fila esteja cheia).
  useEffect(() => {
    if (!open || !clienteId || historico.length > 0 || loading) return;
    setLoading(true);
    void loadClienteHistoricoAction(clienteId, {
      excludeId: atendimentoId,
      limit: 1,
    }).then((r) => {
      setLoading(false);
      if (r.ok) setHistorico(r.atendimentos);
      else setError(r.error);
    });
  }, [open, clienteId, atendimentoId, historico.length, loading]);

  if (!clienteId) {
    return null;
  }

  return (
    <section className="border-t bg-muted/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-sm font-medium hover:bg-muted/40"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <UserIcon className="h-4 w-4 text-muted-foreground" />
          Painel do cliente
        </span>
        {open ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="space-y-4 border-t bg-background px-4 py-3">
          {/* Info básica */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-sm">
              <UserIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="font-medium">{clienteNome ?? "—"}</span>
            </div>
            <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
              <Phone className="h-3.5 w-3.5 shrink-0" />
              <span>{clienteTelefone ?? "—"}</span>
            </div>
            <Link
              href={`/clientes/${clienteId}`}
              className="inline-flex items-center gap-1 text-xs text-brand-primary hover:underline"
            >
              Ver ficha completa
              <ExternalLink className="h-3 w-3" />
            </Link>
          </div>

          {/* Último atendimento anterior — histórico completo via ficha */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <History className="h-3 w-3" />
                Último atendimento
              </h3>
              <Link
                href={`/clientes/${clienteId}`}
                className="text-[10px] text-brand-primary hover:underline"
              >
                ver todos
              </Link>
            </div>

            {loading && (
              <p className="flex items-center gap-1.5 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Carregando…
              </p>
            )}

            {error && (
              <p className="flex items-center gap-1.5 py-2 text-xs text-destructive">
                <AlertCircle className="h-3 w-3" />
                {error}
              </p>
            )}

            {!loading && !error && historico.length === 0 && (
              <p className="py-2 text-xs text-muted-foreground">
                Nenhum atendimento anterior — esta é a primeira interação.
              </p>
            )}

            {!loading && historico.length > 0 && (
              <ul className="space-y-1.5">
                {historico.map((atd) => {
                  const meta = STATUS_META[atd.status as StatusKey];
                  const Icon = meta?.Icon ?? Clock;
                  return (
                    <li key={atd.id}>
                      {/* Não-clicável: re-abrir atendimento via ?focus= ainda
                          não é suportado em page.tsx. Quem quiser detalhe vai
                          pela ficha do cliente (link "ver todos" acima). */}
                      <div className="flex items-start gap-2 rounded-md bg-muted/30 px-2 py-1.5 text-xs">
                        <Icon
                          className={cn(
                            "mt-0.5 h-3.5 w-3.5 shrink-0",
                            meta?.cls ?? ""
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-1">
                            <span className="truncate font-medium">
                              {meta?.label ?? atd.status}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground">
                              #{atd.protocolo ?? atd.id}
                            </span>
                          </div>
                          {atd.classificacao && (
                            <p className="truncate text-muted-foreground">
                              {atd.classificacao}
                            </p>
                          )}
                          <p className="text-[10px] text-muted-foreground">
                            {atd.created_at
                              ? new Date(atd.created_at).toLocaleDateString(
                                  "pt-BR",
                                  {
                                    day: "2-digit",
                                    month: "short",
                                    year: "2-digit",
                                  }
                                )
                              : "—"}
                          </p>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
