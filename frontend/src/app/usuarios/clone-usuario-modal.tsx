"use client";

import { useId, useState, useTransition } from "react";
import { Copy, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { plural } from "@/lib/formato";
import type { Usuario } from "@/lib/api";

import { clonarUsuarioAction } from "./actions";

/**
 * Cria um usuário novo com o mesmo acesso de um existente: perfis,
 * departamentos, conexões, cargo e capacidade. Serve pra contratar a quarta
 * pessoa do mesmo time sem reconfigurar tudo de novo.
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
  const id = useId();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [telefone, setTelefone] = useState("");
  const [erroNome, setErroNome] = useState<string | null>(null);
  const [erroGeral, setErroGeral] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function confirmar() {
    setErroNome(null);
    setErroGeral(null);
    if (!nome.trim()) {
      setErroNome("Informe o nome de quem vai usar esta conta.");
      return;
    }
    start(async () => {
      const r = await clonarUsuarioAction(origem.id, {
        nome: nome.trim(),
        email: email.trim() || null,
        telefone: telefone.trim() || null,
      });
      if (r.ok) onCloned(r.usuario, r.password);
      else setErroGeral(r.error);
    });
  }

  const herda = [
    plural(origem.perfis.length, "perfil", "perfis"),
    plural(origem.departamentos.length, "departamento", "departamentos"),
    plural(origem.conexoes.length, "conexão", "conexões"),
  ].join(", ");

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="size-4 text-primary" />
            Copiar o acesso de {origem.nome || origem.email}
          </DialogTitle>
          <DialogDescription>
            A conta nova nasce com {herda}, além do cargo e da capacidade de
            atendimento. A senha é gerada na hora e aparece a seguir.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Field>
            <FieldLabel htmlFor={`${id}-nome`}>Nome</FieldLabel>
            <Input
              id={`${id}-nome`}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Quem vai usar esta conta"
              aria-invalid={!!erroNome}
              autoFocus
            />
            {erroNome ? <FieldError>{erroNome}</FieldError> : null}
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-email`}>Email (opcional)</FieldLabel>
            <Input
              id={`${id}-email`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nome@empresa.com.br"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-telefone`}>
              Telefone (opcional)
            </FieldLabel>
            <Input
              id={`${id}-telefone`}
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="(62) 99999-9999"
            />
          </Field>
          {erroGeral ? (
            <p className="text-xs text-destructive">{erroGeral}</p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={pending}>
            {pending && <Loader2 className="size-4 animate-spin" />}
            Criar conta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
