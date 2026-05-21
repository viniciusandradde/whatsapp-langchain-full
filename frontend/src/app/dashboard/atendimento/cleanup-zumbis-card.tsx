"use client";

import { useEffect, useState, useTransition } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";

import {
  cleanupZumbisAction,
  previewZumbisAction,
} from "./actions";

interface PreviewState {
  enabled: boolean;
  aguardando_zumbi: number;
  em_andamento_zumbi: number;
  total: number;
  config: {
    enabled: boolean;
    dias_max_aguardando: number;
    dias_max_sem_resposta: number;
  };
}

export function CleanupZumbisCard() {
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [lastResult, setLastResult] = useState<string | null>(null);

  async function loadPreview() {
    try {
      const r = await previewZumbisAction();
      setPreview(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    }
  }

  useEffect(() => {
    void loadPreview();
  }, []);

  function handleCleanup() {
    if (!preview || preview.total === 0) return;
    const ok = confirm(
      `Fechar ${preview.total} atendimento(s) zumbi como abandonado?\n\n` +
        `• Aguardando há >${preview.config.dias_max_aguardando}d: ${preview.aguardando_zumbi}\n` +
        `• Em andamento sem resposta há >${preview.config.dias_max_sem_resposta}d: ${preview.em_andamento_zumbi}\n\n` +
        `Ação irreversível. Continuar?`
    );
    if (!ok) return;

    startTransition(async () => {
      try {
        const r = await cleanupZumbisAction(false);
        setLastResult(
          `✅ ${r.total} fechados (${r.aguardando_fechados} aguardando + ${r.em_andamento_fechados} em andamento)`
        );
        await loadPreview();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro");
      }
    });
  }

  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 text-xs text-rose-300">
        Cleanup indisponível: {error}
      </div>
    );
  }

  if (!preview || !preview.enabled) return null;

  if (preview.total === 0) {
    return (
      <div className="rounded-lg border border-border/40 bg-card/40 p-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">
            🧹 Cleanup: fila limpa ({preview.config.dias_max_aguardando}d / {preview.config.dias_max_sem_resposta}d)
          </span>
          {lastResult && (
            <span className="text-emerald-400">{lastResult}</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <div className="flex items-center justify-between gap-3 text-sm">
        <div className="flex-1">
          <div className="flex items-center gap-2 font-medium text-amber-300">
            <Trash2 className="size-4" />
            {preview.total} atendimentos zumbis na fila
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {preview.aguardando_zumbi} aguardando há &gt;
            {preview.config.dias_max_aguardando}d ·{" "}
            {preview.em_andamento_zumbi} em andamento sem resposta há &gt;
            {preview.config.dias_max_sem_resposta}d
          </div>
          {lastResult && (
            <div className="mt-1 text-xs text-emerald-400">{lastResult}</div>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={handleCleanup}
          disabled={isPending}
          className="gap-1.5"
        >
          {isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Trash2 className="size-3.5" />
          )}
          Limpar agora
        </Button>
      </div>
      <p className="mt-2 text-[10px] text-muted-foreground">
        Cron automático roda a cada 6h. Esse botão força execução imediata.
      </p>
    </div>
  );
}
