"use client";

import { useState } from "react";
import { Check, Copy, KeyRound, MessageCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { ConviteResultado } from "./actions";

interface Props {
  password: string;
  userName: string;
  /** Resultado do convite por WhatsApp, quando foi tentado no criar. */
  convite?: ConviteResultado;
  onClose: () => void;
}

/**
 * A senha aparece uma única vez, então clique fora **não** fecha: perder o
 * diálogo por um clique torto significa resetar de novo, com a pessoa
 * esperando do outro lado.
 *
 * `Escape` e o X continuam fechando de propósito — travar as duas saídas seria
 * prender quem prefere anotar no papel a copiar pra área de transferência.
 */
export function SenhaGeradaModal({ password, userName, convite, onClose }: Props) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(password);
    } catch {
      // Clipboard API exige contexto seguro; em HTTP local cai aqui.
      const ta = document.createElement("textarea");
      ta.value = password;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2500);
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} disablePointerDismissal>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-5 text-warning" />
            Senha gerada
          </DialogTitle>
          <DialogDescription>
            Senha temporária de{" "}
            <span className="font-medium text-foreground">{userName}</span>.
            Ela aparece uma única vez — copie antes de fechar e envie por um
            canal em que você confie.
          </DialogDescription>
        </DialogHeader>

        {convite?.ok && (
          <p className="flex items-start gap-2 rounded-md border border-success/30 bg-success/5 p-3 text-sm">
            <MessageCircle className="mt-0.5 size-4 shrink-0 text-success" />
            <span>
              Convite enviado no WhatsApp{" "}
              <span className="font-medium">{convite.telefone}</span>. A pessoa
              cria a própria senha pelo link — a senha abaixo é só reserva, se
              o link expirar.
            </span>
          </p>
        )}
        {convite && !convite.ok && (
          <p className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 p-3 text-sm">
            <MessageCircle className="mt-0.5 size-4 shrink-0 text-warning" />
            <span>
              O convite pelo WhatsApp não saiu: {convite.erro} Envie a senha
              abaixo pelo canal que preferir.
            </span>
          </p>
        )}

        <div className="flex items-center gap-2">
          <code className="flex-1 rounded-md border border-warning/30 bg-warning/5 px-3 py-2.5 font-mono text-base tracking-wide">
            {password}
          </code>
          <Button
            size="icon"
            variant={copiado ? "outline" : "default"}
            onClick={copiar}
            aria-label="Copiar senha"
          >
            {copiado ? (
              <Check className="size-4 text-success" />
            ) : (
              <Copy className="size-4" />
            )}
          </Button>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>Já anotei, pode fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
