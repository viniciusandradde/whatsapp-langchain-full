"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Hand,
  UserPlus,
  XCircle,
  ExternalLink,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Atendimento, TipoVisualizacao } from "@/lib/api";

import { claimAction, closeAction, transferAction } from "./actions";

interface Props {
  atendimentos: Atendimento[];
  tipo: TipoVisualizacao;
}

const STATUS_LABEL: Record<Atendimento["status"], string> = {
  aguardando: "Aguardando",
  em_andamento: "Em andamento",
  resolvido: "Resolvido",
  abandonado: "Abandonado",
};

function statusVariant(
  status: Atendimento["status"]
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "em_andamento") return "default";
  if (status === "aguardando") return "secondary";
  if (status === "abandonado") return "destructive";
  return "outline";
}

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}m atrás`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h atrás`;
  const d = Math.round(h / 24);
  return `${d}d atrás`;
}

export function AtendimentoList({ atendimentos, tipo }: Props) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function run(action: () => Promise<{ ok: true } | { ok: false; error: string }>, id: number) {
    setBusyId(id);
    setError(null);
    startTransition(async () => {
      const r = await action();
      if (!r.ok) setError(r.error);
      setBusyId(null);
    });
  }

  function handleClaim(a: Atendimento) {
    run(() => claimAction(a.id), a.id);
  }

  function handleClose(a: Atendimento, status: "resolvido" | "abandonado") {
    if (
      !confirm(
        `Fechar atendimento como ${status === "resolvido" ? "resolvido" : "abandonado"}?`
      )
    )
      return;
    run(() => closeAction(a.id, status), a.id);
  }

  function handleTransfer(a: Atendimento) {
    const userId = prompt(
      "ID do operador para transferência (Better Auth user_id):"
    );
    if (!userId) return;
    run(() => transferAction(a.id, userId.trim()), a.id);
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
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {atendimentos.map((a) => {
          const busy = isPending && busyId === a.id;
          const isOpen =
            a.status === "aguardando" || a.status === "em_andamento";
          return (
            <Card key={a.id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">
                      {a.cliente_nome ?? a.cliente_telefone ?? "Cliente"}
                    </CardTitle>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {a.cliente_telefone ?? "—"}
                    </p>
                  </div>
                  <Badge variant={statusVariant(a.status)}>
                    {STATUS_LABEL[a.status]}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <Row label="Atendimento #" value={`${a.id}`} />
                <Row label="Agente" value={a.agente_atual} />
                <Row
                  label="Última mensagem"
                  value={formatRelative(a.last_message_at)}
                />
                {a.assigned_to_user_id && (
                  <Row
                    label="Atribuído a"
                    value={a.assigned_to_user_id}
                    mono
                  />
                )}
              </CardContent>
              <div className="flex flex-wrap items-center justify-end gap-2 px-4 pb-4">
                {a.cliente_id && (
                  <Link
                    href={`/clientes/${a.cliente_id}`}
                    className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  >
                    <ExternalLink className="size-3" />
                    Ficha do cliente
                  </Link>
                )}
                {a.status === "aguardando" && (
                  <Button
                    size="sm"
                    onClick={() => handleClaim(a)}
                    disabled={busy}
                  >
                    <Hand className="size-3.5" />
                    Atender
                  </Button>
                )}
                {isOpen && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleTransfer(a)}
                    disabled={busy}
                  >
                    <UserPlus className="size-3.5" />
                    Transferir
                  </Button>
                )}
                {isOpen && (
                  <>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleClose(a, "resolvido")}
                      disabled={busy}
                    >
                      <CheckCircle2 className="size-3.5" />
                      Resolver
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleClose(a, "abandonado")}
                      disabled={busy}
                    >
                      <XCircle className="size-3.5" />
                      Abandonar
                    </Button>
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "truncate font-mono text-xs" : "truncate"}>
        {value}
      </span>
    </div>
  );
}
