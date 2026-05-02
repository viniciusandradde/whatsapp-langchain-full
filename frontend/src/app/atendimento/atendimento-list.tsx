"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Atendimento, TipoVisualizacao } from "@/lib/api";

import { AtendimentoDrawer } from "./atendimento-drawer";

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
  const [active, setActive] = useState<Atendimento | null>(null);

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
    <>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {atendimentos.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setActive(a)}
            className="text-left transition hover:scale-[1.01]"
          >
            <Card className="h-full hover:border-foreground/20">
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
            </Card>
          </button>
        ))}
      </div>

      {active && (
        <AtendimentoDrawer
          atendimento={active}
          onClose={() => setActive(null)}
        />
      )}
    </>
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
