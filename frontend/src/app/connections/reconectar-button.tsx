"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { QrCode } from "lucide-react";

import { Button } from "@/components/ui/button";

import { EvolutionQRModal, type Reconectar } from "./evolution-qr-modal";

interface Props {
  conexao: Reconectar & { provider: string; connectionState?: string | null };
  /** `icon` = botão compacto da lista; `full` = botão com texto na página. */
  variante?: "icon" | "full";
}

/** Estados em que reparear faz sentido: tudo que não é sessão aberta. */
export function precisaReconectar(
  provider: string,
  connectionState?: string | null
): boolean {
  if (provider !== "evolution") return false;
  return !["open", "ready"].includes(connectionState ?? "");
}

/** Abre o modal de QR/código para uma conexão Evolution que já existe.
 *
 *  Até 21/09/2026 o painel só pareava no fluxo "Nova conexão": quando o
 *  aparelho era desvinculado, o jeito era apagar a conexão e criar outra —
 *  perdendo agente/modo/anti-ban/baseline do monitor presos ao id antigo. */
export function ReconectarButton({ conexao, variante = "full" }: Props) {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);

  if (!precisaReconectar(conexao.provider, conexao.connectionState)) {
    return null;
  }

  return (
    <>
      {variante === "icon" ? (
        <Button
          variant="ghost"
          size="sm"
          title="Reconectar (QR ou código)"
          aria-label="Reconectar"
          onClick={() => setAberto(true)}
          className="h-7 w-7 p-0 text-emerald-500 hover:text-emerald-400"
        >
          <QrCode className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <Button onClick={() => setAberto(true)} className="gap-1.5">
          <QrCode className="h-4 w-4" />
          Reconectar
        </Button>
      )}
      {aberto && (
        <EvolutionQRModal
          reconectar={{
            conexaoId: conexao.conexaoId,
            displayName: conexao.displayName,
          }}
          onClose={(refresh) => {
            setAberto(false);
            if (refresh) router.refresh();
          }}
        />
      )}
    </>
  );
}
