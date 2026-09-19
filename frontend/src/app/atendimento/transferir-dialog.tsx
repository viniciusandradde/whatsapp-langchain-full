"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AtendenteStatus, Departamento } from "@/lib/api";
import { cn } from "@/lib/utils";

import { loadAtendentesOnlineAction, loadDepartamentosAction } from "./actions";

/**
 * Transferência (Sprint V) em diálogo do kit — antes era um popover à mão
 * preso ao rodapé de ações, com `fixed inset-0` no celular. Dois modos:
 * departamento (entra na fila do setor; o cliente recebe aviso) e atendente
 * online (muda o dono, mantém em andamento).
 *
 * Carrega departamentos + atendentes online só ao abrir, pelo cache do
 * Query (sem o `.length === 0` como sinal de "não carreguei" — o bug da
 * rajada #133).
 */
export function TransferirDialog({
  aberto,
  onAbertoChange,
  pendente,
  onConfirmar,
}: {
  aberto: boolean;
  onAbertoChange: (v: boolean) => void;
  pendente: boolean;
  onConfirmar: (destino: { departamentoId: number } | { userId: string }) => void;
}) {
  const [modo, setModo] = useState<"departamento" | "atendente">("departamento");
  const [depId, setDepId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  // TanStack Query: carrega ao abrir, cacheia 60 s (abrir de novo não refaz
  // as duas Server Actions) e não precisa de setState em efeito.
  const { data, isLoading: carregando } = useQuery({
    queryKey: ["transferir-destinos"],
    queryFn: async () => {
      const [d, a] = await Promise.all([loadDepartamentosAction(), loadAtendentesOnlineAction()]);
      if (!d.ok) throw new Error(d.error);
      if (!a.ok) throw new Error(a.error);
      return { departamentos: d.departamentos, atendentes: a.atendentes };
    },
    enabled: aberto,
    staleTime: 60_000,
  });
  const departamentos: Departamento[] = data?.departamentos ?? [];
  const atendentes: AtendenteStatus[] = data?.atendentes ?? [];

  const podeConfirmar = modo === "departamento" ? !!depId : !!userId;

  function confirmar() {
    if (modo === "departamento") {
      if (!depId) return;
      onConfirmar({ departamentoId: Number(depId) });
    } else {
      if (!userId) return;
      onConfirmar({ userId });
    }
    onAbertoChange(false);
  }

  return (
    <Dialog open={aberto} onOpenChange={onAbertoChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Transferir atendimento</DialogTitle>
          <DialogDescription>
            Para um setor (entra na fila e o cliente é avisado) ou direto para um
            atendente online.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-0.5" role="tablist">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            role="tab"
            aria-selected={modo === "departamento"}
            className={cn(modo === "departamento" && "bg-background shadow-sm")}
            onClick={() => setModo("departamento")}
          >
            <Building2 className="size-3.5" />
            Departamento
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            role="tab"
            aria-selected={modo === "atendente"}
            className={cn(modo === "atendente" && "bg-background shadow-sm")}
            onClick={() => setModo("atendente")}
          >
            <UserRound className="size-3.5" />
            Atendente
          </Button>
        </div>

        {modo === "departamento" ? (
          <Select value={depId} onValueChange={(v: string | null) => setDepId(v)}>
            <SelectTrigger className="w-full" aria-label="Departamento de destino">
              <SelectValue
                placeholder={
                  carregando
                    ? "Carregando…"
                    : departamentos.length === 0
                      ? "Nenhum departamento ativo"
                      : "Selecione o departamento"
                }
              >
                {(v: string | null) =>
                  departamentos.find((d) => String(d.id) === v)?.nome ?? "Selecione o departamento"
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {departamentos.map((d) => (
                <SelectItem key={d.id} value={String(d.id)}>
                  {d.nome}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Select value={userId} onValueChange={(v: string | null) => setUserId(v)}>
            <SelectTrigger className="w-full" aria-label="Atendente online de destino">
              <SelectValue
                placeholder={
                  carregando
                    ? "Carregando…"
                    : atendentes.length === 0
                      ? "Nenhum atendente online no momento"
                      : "Selecione o atendente"
                }
              >
                {(v: string | null) => {
                  const a = atendentes.find((x) => x.user_id === v);
                  return a ? a.nome || a.email || a.user_id : "Selecione o atendente";
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {atendentes.map((a) => (
                <SelectItem key={a.user_id} value={a.user_id}>
                  {a.nome || a.email || a.user_id}
                  {a.count_atendimentos_abertos > 0
                    ? ` (${a.count_atendimentos_abertos} abertos)`
                    : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onAbertoChange(false)} disabled={pendente}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={pendente || !podeConfirmar}>
            Transferir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
