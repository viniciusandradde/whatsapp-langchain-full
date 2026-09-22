"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { wabaSincronizarAction } from "../actions";

/**
 * Coexistence (mig 200): pede de novo à Meta os contatos e o histórico do
 * WhatsApp Business. A Meta só aceita em até 24 horas depois da conexão —
 * serve para quando o pedido do cadastro falhou.
 */
export function SincronizarButton({ conexaoId }: { conexaoId: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [erro, setErro] = useState<string | null>(null);

  return (
    <div className="space-y-1">
      <Button
        size="sm"
        variant="outline"
        className="gap-2"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            setErro(null);
            const r = await wabaSincronizarAction(conexaoId);
            if (r.ok) {
              toast.success("Sincronização pedida à Meta");
              router.refresh();
            } else {
              setErro(r.error);
            }
          })
        }
      >
        <RefreshCw className={pending ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        Sincronizar contatos e histórico
      </Button>
      {erro && <p className="text-xs text-destructive">{erro}</p>}
    </div>
  );
}
