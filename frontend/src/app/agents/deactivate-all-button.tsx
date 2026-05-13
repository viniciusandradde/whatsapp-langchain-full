"use client";

import { useState, useTransition } from "react";
import { Loader2, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";

import { deactivateAllAgentesAction } from "./actions";

interface Props {
  /** Quantidade de agentes ativos hoje. Se 0, o botão é desabilitado. */
  ativosCount: number;
}

export function DeactivateAllAgentesButton({ ativosCount }: Props) {
  const [pending, start] = useTransition();
  const [feedback, setFeedback] = useState<string | null>(null);

  function handleClick() {
    if (ativosCount === 0) return;
    const msg =
      `Desativar TODOS os ${ativosCount} agentes IA ativos?\n\n` +
      `Atendimentos novos vão pro menu legacy / fallback até reativar.\n` +
      `Você pode reativar individualmente em "Editar" de cada agente.`;
    if (!confirm(msg)) return;
    setFeedback(null);
    start(async () => {
      const r = await deactivateAllAgentesAction();
      if (r.ok) {
        setFeedback(`✓ ${r.qtde} agentes desativados.`);
      } else if (r.error) {
        setFeedback(`Erro: ${r.error}`);
      } else {
        setFeedback(
          `${r.qtde} desativados, ${r.falhas.length} falhas: ` +
            r.falhas.slice(0, 3).join(", ") +
            (r.falhas.length > 3 ? "..." : "")
        );
      }
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="outline"
        size="sm"
        onClick={handleClick}
        disabled={pending || ativosCount === 0}
        title={
          ativosCount === 0
            ? "Nenhum agente ativo pra desativar"
            : `Desativar todos os ${ativosCount} agentes ativos`
        }
      >
        {pending ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <PowerOff className="size-4" />
        )}
        Desativar todos ({ativosCount})
      </Button>
      {feedback && (
        <span className="text-xs text-muted-foreground">{feedback}</span>
      )}
    </div>
  );
}
