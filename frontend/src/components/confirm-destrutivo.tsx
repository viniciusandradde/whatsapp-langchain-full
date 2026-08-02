"use client";

import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Confirmação de ação destrutiva — no lugar do `confirm()` do navegador.
 *
 * O painel tinha 46 `confirm()` e 36 `alert()`. A caixa do navegador não aceita
 * tema, não destaca o nome do que vai ser apagado e, no celular, aparece como
 * diálogo do sistema no topo da tela. Para "apagar conexão" ou "promover 8.596
 * contatos", OK/Cancelar cinza é o caminho mais curto pro incidente.
 *
 * Regra do contrato (C4): ação destrutiva mostra **o nome do objeto**; ação em
 * massa acima de 50 registros exige **digitar o total** — quem clica sem ler
 * não consegue confirmar por acidente.
 */
export function ConfirmDestrutivo({
  aberto,
  onAbertoChange,
  titulo,
  objeto,
  descricao,
  rotuloAcao = "Excluir",
  tom = "destrutivo",
  exigeDigitar,
  onConfirmar,
}: {
  aberto: boolean;
  onAbertoChange: (v: boolean) => void;
  titulo: string;
  /** Nome do que será afetado — aparece em destaque no corpo. */
  objeto?: string;
  descricao?: React.ReactNode;
  rotuloAcao?: string;
  /**
   * `destrutivo` (default) pinta o botão de vermelho e avisa que não dá pra
   * desfazer. `serio` é pra confirmação que merece uma pausa mas não apaga
   * nada — reativar acesso, por exemplo. Vermelho em tudo é vermelho em nada.
   */
  tom?: "destrutivo" | "serio";
  /** Quando definido, o botão só libera se o usuário digitar exatamente isto. */
  exigeDigitar?: string;
  onConfirmar: () => void | Promise<void>;
}) {
  const [digitado, setDigitado] = useState("");
  const liberado = !exigeDigitar || digitado.trim() === exigeDigitar;

  function fechar(v: boolean) {
    if (!v) setDigitado("");
    onAbertoChange(v);
  }

  return (
    <AlertDialog open={aberto} onOpenChange={fechar}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{titulo}</AlertDialogTitle>
          {/* `render` é a composição do Base UI (o `asChild` do Radix não
              existe aqui) — precisa de <div> porque o corpo tem parágrafos. */}
          <AlertDialogDescription render={<div className="space-y-2" />}>
            {objeto ? (
              <p>
                Isto vai afetar{" "}
                <strong className="font-medium text-foreground">{objeto}</strong>
                .
              </p>
            ) : null}
            {descricao ? <div>{descricao}</div> : null}
            {tom === "destrutivo" ? <p>Esta ação não pode ser desfeita.</p> : null}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {exigeDigitar ? (
          <div className="space-y-2">
            <Label htmlFor="confirmacao-digitada">
              Digite <code className="font-mono">{exigeDigitar}</code> para
              confirmar
            </Label>
            <Input
              id="confirmacao-digitada"
              value={digitado}
              onChange={(e) => setDigitado(e.target.value)}
              autoComplete="off"
            />
          </div>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          {/* Vermelho, não a cor primária: o botão que apaga não pode ter a
              mesma aparência do botão que salva. `AlertDialogAction` herda o
              `default` do Button, que é a marca. */}
          <AlertDialogAction
            variant={tom === "destrutivo" ? "destructive" : "default"}
            disabled={!liberado}
            onClick={async () => {
              await onConfirmar();
              fechar(false);
            }}
          >
            {rotuloAcao}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
