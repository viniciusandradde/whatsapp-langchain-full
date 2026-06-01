"use client";

import { useEffect, useState, useTransition } from "react";
import { Loader2, PowerOff, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AtendenteStatus, Usuario } from "@/lib/api";

import {
  loadAtendentesAction,
  loadDepartamentosOptionsAction,
  setStatusUsuarioAction,
  type DepartamentoOption,
} from "./actions";

type Modo = "none" | "reassign" | "departamento";

/**
 * Desativa um usuário com tratamento dos atendimentos abertos (paridade
 * ZigChat `transferencia_usuario_id`): só desativar, reatribuir p/ outro
 * atendente, ou devolver à fila de um departamento.
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
  const [modo, setModo] = useState<Modo>("none");
  const [atendentes, setAtendentes] = useState<AtendenteStatus[]>([]);
  const [departamentos, setDepartamentos] = useState<DepartamentoOption[]>([]);
  const [targetUser, setTargetUser] = useState("");
  const [deptoId, setDeptoId] = useState<number | "">("");
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
      setError("Escolha um atendente pra receber os atendimentos.");
      return;
    }
    if (modo === "departamento" && !deptoId) {
      setError("Escolha um departamento.");
      return;
    }
    start(async () => {
      const r = await setStatusUsuarioAction(usuario.id, {
        status: "disabled",
        on_disable: modo,
        target_user_id: modo === "reassign" ? targetUser : undefined,
        departamento_id:
          modo === "departamento" ? Number(deptoId) : undefined,
      });
      if (r.ok) onDone(r.data.transferidos);
      else setError(r.error);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-obsidian-900 shadow-vsa-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
            <PowerOff className="size-4" />
            Desativar {usuario.nome || usuario.email}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-3 px-4 py-4 text-sm">
          <p className="text-muted-foreground">
            As sessões ativas serão encerradas. O que fazer com os atendimentos
            abertos atribuídos a este usuário?
          </p>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              checked={modo === "none"}
              onChange={() => setModo("none")}
              className="mt-1"
            />
            <span>Apenas desativar (deixa os atendimentos como estão).</span>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              checked={modo === "reassign"}
              onChange={() => setModo("reassign")}
              className="mt-1"
            />
            <span className="flex-1">
              Reatribuir para outro atendente
              {modo === "reassign" && (
                <select
                  value={targetUser}
                  onChange={(e) => setTargetUser(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-white/10 bg-obsidian-800 px-2 py-1 text-sm"
                >
                  <option value="">Selecione…</option>
                  {atendentes.map((a) => (
                    <option key={a.user_id} value={a.user_id}>
                      {a.nome || a.email || a.user_id}
                      {a.atendente_status === "online" ? " • online" : ""} (
                      {a.count_atendimentos_abertos} abertos)
                    </option>
                  ))}
                </select>
              )}
            </span>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              checked={modo === "departamento"}
              onChange={() => setModo("departamento")}
              className="mt-1"
            />
            <span className="flex-1">
              Devolver à fila de um departamento
              {modo === "departamento" && (
                <select
                  value={deptoId}
                  onChange={(e) =>
                    setDeptoId(e.target.value ? Number(e.target.value) : "")
                  }
                  className="mt-1 block w-full rounded-md border border-white/10 bg-obsidian-800 px-2 py-1 text-sm"
                >
                  <option value="">Selecione…</option>
                  {departamentos.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nome}
                    </option>
                  ))}
                </select>
              )}
            </span>
          </label>

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-white/10 px-4 py-3">
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button variant="destructive" onClick={confirmar} disabled={pending}>
            {pending && <Loader2 className="mr-1 size-4 animate-spin" />}
            Desativar
          </Button>
        </div>
      </div>
    </div>
  );
}
