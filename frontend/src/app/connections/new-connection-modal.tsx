"use client";

import { useState } from "react";
import { Cloud, MessageSquare, Smartphone, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import { EvolutionQRModal } from "./evolution-qr-modal";
import { TwilioFormModal } from "./twilio-form-modal";
import { WabaOAuthButton } from "./waba-oauth-button";

interface Props {
  onClose: (refresh: boolean) => void;
}

type Step = "pick" | "waba" | "evolution" | "twilio";

export function NewConnectionModal({ onClose }: Props) {
  const [step, setStep] = useState<Step>("pick");
  const [wabaError, setWabaError] = useState<string | null>(null);

  if (step === "twilio") {
    return (
      <TwilioFormModal
        onClose={(refresh) => {
          if (refresh) onClose(true);
          else setStep("pick");
        }}
      />
    );
  }

  if (step === "evolution") {
    return (
      <EvolutionQRModal
        onClose={(refresh) => {
          if (refresh) onClose(true);
          else setStep("pick");
        }}
      />
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-2xl rounded-lg border border-border/40 bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 className="text-lg font-semibold">Nova conexão WhatsApp</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-3 p-4">
          <p className="text-sm text-muted-foreground">
            Escolha o tipo de integração WhatsApp:
          </p>

          {/* WABA — Recomendado */}
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
            <div className="flex items-start gap-3">
              <div className="rounded-md bg-emerald-500/20 p-2">
                <Cloud className="h-5 w-5 text-emerald-400" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">WhatsApp Oficial</span>
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">
                    Recomendado
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Conexão via Meta WhatsApp Cloud API (Embedded Signup). 1
                  clique, sem QR. Suporta templates aprovados e mensagens
                  fora da janela 24h.
                </p>
                <div className="mt-3">
                  <WabaOAuthButton
                    onSuccess={() => onClose(true)}
                    onError={(e) => setWabaError(e)}
                  />
                </div>
                {wabaError && (
                  <p className="mt-2 text-xs text-rose-400">{wabaError}</p>
                )}
              </div>
            </div>
          </div>

          {/* Evolution */}
          <button
            onClick={() => setStep("evolution")}
            className="group flex w-full items-start gap-3 rounded-lg border border-border/40 p-4 text-left transition-colors hover:bg-muted/20"
          >
            <div className="rounded-md bg-blue-500/20 p-2">
              <Smartphone className="h-5 w-5 text-blue-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium">Evolution API</div>
              <p className="mt-1 text-xs text-muted-foreground">
                WhatsApp via Baileys (não-oficial). Escaneie QR code com
                seu celular. Funciona com qualquer número WhatsApp comum.
              </p>
            </div>
          </button>

          {/* Twilio */}
          <button
            onClick={() => setStep("twilio")}
            className="group flex w-full items-start gap-3 rounded-lg border border-border/40 p-4 text-left transition-colors hover:bg-muted/20"
          >
            <div className="rounded-md bg-rose-500/20 p-2">
              <MessageSquare className="h-5 w-5 text-rose-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium">Twilio</div>
              <p className="mt-1 text-xs text-muted-foreground">
                Sandbox para desenvolvimento ou número Twilio prod. Útil
                se você já tem conta Twilio ativa.
              </p>
            </div>
          </button>

        </div>
      </div>
    </div>
  );
}
