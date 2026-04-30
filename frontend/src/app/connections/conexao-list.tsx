"use client";

import { useState, useTransition } from "react";
import { Plus, PowerOff, Pencil } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Conexao } from "@/lib/api";

import { disableConexaoAction } from "./actions";
import { ConexaoForm } from "./conexao-form";

interface Props {
  conexoes: Conexao[];
}

export function ConexaoList({ conexoes }: Props) {
  const [editing, setEditing] = useState<Conexao | "new" | null>(null);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleDisable(id: number) {
    if (!confirm("Desativar essa conexão? Pode reativar editando depois.")) return;
    setError(null);
    startTransition(async () => {
      const result = await disableConexaoAction(id);
      if (!result.ok) setError(result.error);
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Cada linha WhatsApp (Twilio sandbox/prod, WABA) liga uma empresa a
          um número de origem. O webhook resolve empresa + agente pelo
          número de destino.
        </p>
        {editing !== "new" && (
          <Button onClick={() => setEditing("new")} variant="default">
            <Plus className="size-4" />
            Nova conexão
          </Button>
        )}
      </div>

      {editing === "new" && (
        <ConexaoForm onDone={() => setEditing(null)} />
      )}
      {editing && editing !== "new" && (
        <ConexaoForm initial={editing} onDone={() => setEditing(null)} />
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {conexoes.length === 0 && !editing && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhuma conexão cadastrada</p>
          <p className="mt-1 text-sm">
            Adicione uma linha WhatsApp pra a empresa receber mensagens.
          </p>
        </div>
      )}

      {conexoes.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {conexoes.map((c) => (
            <Card key={c.id}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">
                      {c.display_name ?? c.from_number}
                    </CardTitle>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {c.from_number}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Badge
                      variant={
                        c.status === "active"
                          ? "default"
                          : c.status === "error"
                            ? "destructive"
                            : "outline"
                      }
                    >
                      {c.status}
                    </Badge>
                    {c.is_default && (
                      <Badge variant="secondary">default</Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <Row label="Provider" value={c.provider} />
                <Row label="Default agent" value={c.default_agent_id} />
                {c.sid && <Row label="SID" value={c.sid} mono />}
              </CardContent>
              <div className="flex items-center justify-end gap-2 px-4 pb-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditing(c)}
                  disabled={isPending}
                >
                  <Pencil className="size-3.5" />
                  Editar
                </Button>
                {c.status !== "disabled" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDisable(c.id)}
                    disabled={isPending}
                  >
                    <PowerOff className="size-3.5" />
                    Desativar
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
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
      <span className={mono ? "font-mono text-xs" : ""}>{value}</span>
    </div>
  );
}
