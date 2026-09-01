"use client";

import { useState } from "react";
import { Copy, MoreVertical, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * Menu de ações por bolha da timeline — paridade com o toque longo do app
 * Android (`MenuBolha.kt`). No desktop o gesto é hover no "…" ou clique
 * direito na bolha.
 *
 * As guardas espelham o app: bolha apagada/erro é inerte (quem monta as
 * bolhas nem chama este componente com ações), Copiar só quando há texto, e
 * Editar/Apagar só quando o servidor disse que pode
 * (`pode_editar_resposta`/`pode_apagar_resposta`). Os flags são calculados na
 * listagem e ficam velhos numa timeline aberta há horas — por isso o backend
 * revalida a janela no clique e a UI apenas repassa a frase do 400.
 */
export function BolhaMenu({
  children,
  copiarTexto,
  podeEditar = false,
  podeApagar = false,
  onEditar,
  onApagar,
}: {
  children: React.ReactNode;
  /** Texto que o item Copiar leva pro clipboard; vazio/null esconde o item. */
  copiarTexto?: string | null;
  podeEditar?: boolean;
  podeApagar?: boolean;
  onEditar?: () => void;
  onApagar?: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  const temCopiar = Boolean(copiarTexto?.trim());
  const temEditar = podeEditar && Boolean(onEditar);
  const temApagar = podeApagar && Boolean(onApagar);
  if (!temCopiar && !temEditar && !temApagar) return <>{children}</>;

  async function copiar() {
    if (!copiarTexto) return;
    try {
      await navigator.clipboard.writeText(copiarTexto);
      toast.success("Mensagem copiada");
    } catch {
      toast.error("Não foi possível copiar. Selecione o texto manualmente.");
    }
  }

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <div
          className="group/bolha relative"
          onContextMenu={(e) => {
            e.preventDefault();
            setOpen(true);
          }}
        >
          {children}
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label="Ações da mensagem"
                className={cn(
                  "absolute -right-1.5 -top-1.5 rounded-full border bg-background p-0.5 text-muted-foreground shadow-sm transition-opacity hover:text-foreground",
                  open
                    ? "opacity-100"
                    : "opacity-0 focus-visible:opacity-100 group-hover/bolha:opacity-100"
                )}
              >
                <MoreVertical className="size-3.5" />
              </button>
            }
          />
        </div>
        <DropdownMenuContent align="end" className="min-w-44">
          {temCopiar && (
            <DropdownMenuItem onClick={() => void copiar()}>
              <Copy /> Copiar
            </DropdownMenuItem>
          )}
          {temEditar && (
            <DropdownMenuItem onClick={onEditar}>
              <Pencil /> Editar
            </DropdownMenuItem>
          )}
          {temApagar && (
            <DropdownMenuItem
              variant="destructive"
              onClick={() => setConfirmando(true)}
            >
              <Trash2 /> Apagar para todos
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDestrutivo
        aberto={confirmando}
        onAbertoChange={setConfirmando}
        titulo="Apagar mensagem para todos?"
        descricao="A mensagem some do WhatsApp do cliente. O texto continua registrado aqui, marcado como apagado, para auditoria."
        rotuloAcao="Apagar"
        onConfirmar={() => void onApagar?.()}
      />
    </>
  );
}
