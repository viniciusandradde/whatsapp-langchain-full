"use client";

import { useState, useTransition } from "react";
import { Captions } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

import { patchConexaoAction } from "../actions";

interface Props {
  conexaoId: number;
  initialAtivo: boolean;
}

/**
 * Transcrição automática de áudio (mig 169).
 *
 * Existe porque conexão em modo manual (o default) nunca transcreve: a
 * transcrição morava só no preprocess do agente IA. Ligado, o worker
 * transcreve toda nota de voz recebida e o texto aparece na timeline —
 * mesmo sem nenhum agente responder. Custa uma chamada de LLM por áudio.
 */
export function TranscricaoPanel({ conexaoId, initialAtivo }: Props) {
  const [ativo, setAtivo] = useState(initialAtivo);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();

  function handleToggle(next: boolean) {
    setMsg(null);
    setAtivo(next);
    startSaving(async () => {
      const r = await patchConexaoAction(conexaoId, {
        transcrever_audio_sempre: next,
      });
      if (!r.ok) {
        setAtivo(!next);
        setMsg(`Erro: ${r.error}`);
        return;
      }
      setMsg("✓ Salvo.");
    });
  }

  return (
    <div className="rounded-lg border border-border/40 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Captions className="h-5 w-5 text-primary" />
        <div>
          <div className="font-medium">Transcrição de áudio</div>
          <p className="text-xs text-muted-foreground">
            Transcreve automaticamente toda nota de voz recebida nesta
            conexão, mesmo quando nenhum agente vai responder (modo manual).
            O texto aparece na conversa, abaixo do player. Desligado, cada
            áudio ainda pode ser transcrito pelo botão na própria mensagem.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Checkbox
          id="transcrever-audio-sempre"
          checked={ativo}
          onCheckedChange={(v) => handleToggle(v === true)}
          disabled={saving}
        />
        <Label
          htmlFor="transcrever-audio-sempre"
          className="text-sm font-normal"
        >
          Transcrever automaticamente ao receber áudio
        </Label>
      </div>

      {msg && (
        <p
          className={
            msg.startsWith("✓")
              ? "text-xs text-muted-foreground"
              : "text-xs text-destructive"
          }
        >
          {msg}
        </p>
      )}
    </div>
  );
}
