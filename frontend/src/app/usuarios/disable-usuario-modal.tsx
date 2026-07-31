"use client";

import { useEffect, useId, useState, useTransition } from "react";
import { Loader2, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { plural } from "@/lib/formato";
import type { AtendenteStatus, Usuario } from "@/lib/api";

import {
  loadAtendentesAction,
  loadDepartamentosOptionsAction,
  setStatusUsuarioAction,
  type DepartamentoOption,
} from "./actions";

type Modo = "none" | "reassign" | "departamento";

/**
 * Tira o acesso de alguém e decide o destino das conversas que estavam com
 * essa pessoa: deixar como estão, passar pra outro atendente, ou devolver pra
 * fila de um departamento.
 *
 * A escolha existe porque desativar sem decidir isso é o caminho conhecido pra
 * conversa órfã — ninguém é dono, ninguém responde, e o cliente fica esperando.
 */
export function DisableUsuarioModal({
  usuario,
  onClose,
  onDone,
}: {
  usuario: Usuario;
  onClose: () => void;
  onDone: (transferidos: number) => void;
}) {
  const id = useId();
  const [modo, setModo] = useState<Modo>("none");
  const [atendentes, setAtendentes] = useState<AtendenteStatus[]>([]);
  const [departamentos, setDepartamentos] = useState<DepartamentoOption[]>([]);
  const [targetUser, setTargetUser] = useState("");
  const [deptoId, setDeptoId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  useEffect(() => {
    loadAtendentesAction().then((r) => {
      if (r.ok) {
        setAtendentes(
          r.data.filter((a) => a.user_id !== usuario.id && a.is_active)
        );
      }
    });
    loadDepartamentosOptionsAction().then((r) => {
      if (r.ok) setDepartamentos(r.data);
    });
  }, [usuario.id]);

  function confirmar() {
    setError(null);
    if (modo === "reassign" && !targetUser) {
      setError("Escolha quem vai receber as conversas.");
      return;
    }
    if (modo === "departamento" && !deptoId) {
      setError("Escolha o departamento que vai receber as conversas.");
      return;
    }
    start(async () => {
      const r = await setStatusUsuarioAction(usuario.id, {
        status: "disabled",
        on_disable: modo,
        target_user_id: modo === "reassign" ? targetUser : undefined,
        departamento_id: modo === "departamento" ? Number(deptoId) : undefined,
      });
      if (r.ok) onDone(r.data.transferidos);
      else setError(r.error);
    });
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <PowerOff className="size-4" />
            Tirar o acesso de {usuario.nome || usuario.email}
          </DialogTitle>
          <DialogDescription>
            As sessões abertas caem em segundos. Escolha o que acontece com as
            conversas que estavam com esta pessoa.
          </DialogDescription>
        </DialogHeader>

        <RadioGroup
          value={modo}
          onValueChange={(v) => setModo(v as Modo)}
          className="gap-3"
        >
          <div className="flex items-start gap-2">
            <RadioGroupItem value="none" id={`${id}-none`} className="mt-0.5" />
            <Label htmlFor={`${id}-none`} className="font-normal">
              Deixar como estão — continuam atribuídas a quem perdeu o acesso.
            </Label>
          </div>

          <div className="flex items-start gap-2">
            <RadioGroupItem
              value="reassign"
              id={`${id}-reassign`}
              className="mt-0.5"
            />
            <div className="flex-1 space-y-2">
              <Label htmlFor={`${id}-reassign`} className="font-normal">
                Passar para outro atendente
              </Label>
              {modo === "reassign" && (
                <Select
                  value={targetUser}
                  onValueChange={(v) => setTargetUser(v ?? "")}
                >
                  <SelectTrigger className="w-full">
                    {/* Sem a função, o gatilho mostraria o `user_id` — um
                        UUID. O rótulo tem que ser resolvido pela lista. */}
                    <SelectValue placeholder="Escolha o atendente…">
                      {(v: string | null) =>
                        v
                          ? (() => {
                              const a = atendentes.find((x) => x.user_id === v);
                              return a?.nome || a?.email || "Escolha o atendente…";
                            })()
                          : "Escolha o atendente…"
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {atendentes.map((a) => (
                      <SelectItem key={a.user_id} value={a.user_id}>
                        {a.nome || a.email || a.user_id}
                        {a.atendente_status === "online" ? " · online" : ""} ·{" "}
                        {plural(
                          a.count_atendimentos_abertos,
                          "conversa aberta",
                          "conversas abertas"
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>

          <div className="flex items-start gap-2">
            <RadioGroupItem
              value="departamento"
              id={`${id}-depto`}
              className="mt-0.5"
            />
            <div className="flex-1 space-y-2">
              <Label htmlFor={`${id}-depto`} className="font-normal">
                Devolver para a fila de um departamento
              </Label>
              {modo === "departamento" && (
                <Select
                  value={deptoId}
                  onValueChange={(v) => setDeptoId(v ?? "")}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Escolha o departamento…">
                      {(v: string | null) =>
                        departamentos.find((d) => String(d.id) === v)?.nome ??
                        "Escolha o departamento…"
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
              )}
            </div>
          </div>
        </RadioGroup>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button variant="destructive" onClick={confirmar} disabled={pending}>
            {pending && <Loader2 className="size-4 animate-spin" />}
            Tirar o acesso
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
