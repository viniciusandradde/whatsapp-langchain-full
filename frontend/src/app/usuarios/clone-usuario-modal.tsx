"use client";

import { useState, useTransition } from "react";
import { Copy, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Usuario } from "@/lib/api";

import { clonarUsuarioAction } from "./actions";

/**
 * Clona um usuário existente (paridade ZigChat `replicarUsuario`): copia
 * perfis, departamentos, conexões, role e capacidade. Onboarding rápido.
 */
export function CloneUsuarioModal({
  origem,
  onClose,
  onCloned,
}: {
  origem: Usuario;
  onClose: () => void;
  onCloned: (usuario: Usuario, password: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [telefone, setTelefone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function confirmar() {
    setError(null);
    if (!nome.trim()) {
      setError("Informe o nome do novo usuário.");
      return;
    }
    start(async () => {
      const r = await clonarUsuarioAction(origem.id, {
        nome: nome.trim(),
        email: email.trim() || null,
        telefone: telefone.trim() || null,
      });
      if (r.ok) onCloned(r.usuario, r.password);
      else setError(r.error);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-obsidian-900 shadow-vsa-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Copy className="size-4 text-brand-primary" />
            Clonar {origem.nome || origem.email}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-3 px-4 py-4 text-sm">
          <p className="text-xs text-muted-foreground">
            Copia perfis ({origem.perfis.length}), departamentos (
            {origem.departamentos.length}), conexões ({origem.conexoes.length}),
            cargo e capacidade. Uma senha nova será gerada.
          </p>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Nome *</label>
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5 text-sm"
              placeholder="Nome do novo usuário"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5 text-sm"
              placeholder="opcional"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Telefone</label>
            <input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5 text-sm"
              placeholder="opcional"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-white/10 px-4 py-3">
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={pending}>
            {pending && <Loader2 className="mr-1 size-4 animate-spin" />}
            Clonar
          </Button>
        </div>
      </div>
    </div>
  );
}
