"use client";

import { useId, useState } from "react";
import { Cloud, Smartphone, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { WabaModo } from "@/lib/api";

import { EvolutionQRModal } from "./evolution-qr-modal";
import { WabaOAuthButton } from "./waba-oauth-button";

interface Props {
  onClose: (refresh: boolean) => void;
}

type Step = "pick" | "waba" | "evolution";

export function NewConnectionModal({ onClose }: Props) {
  const [step, setStep] = useState<Step>("pick");
  const [wabaError, setWabaError] = useState<string | null>(null);
  const [wabaModo, setWabaModo] = useState<WabaModo>("cloud_api");
  const id = useId();

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
                  Conexão oficial da Meta, sem QR. Suporta modelos de
                  mensagem aprovados e mensagens fora da janela de 24 horas.
                </p>
                <RadioGroup
                  value={wabaModo}
                  onValueChange={(v) => {
                    setWabaModo(v as WabaModo);
                    setWabaError(null);
                  }}
                  className="mt-3 gap-3"
                  aria-label="Como o número vai ser usado"
                >
                  <div className="flex items-start gap-2">
                    <RadioGroupItem
                      value="cloud_api"
                      id={`${id}-cloud`}
                      className="mt-0.5"
                    />
                    <Label
                      htmlFor={`${id}-cloud`}
                      className="flex-col items-start gap-0.5 font-normal"
                    >
                      <span className="font-medium">WhatsApp Cloud API</span>
                      <span className="text-xs text-muted-foreground">
                        Número dedicado à API oficial.
                      </span>
                    </Label>
                  </div>
                  <div className="flex items-start gap-2">
                    <RadioGroupItem
                      value="coexistence"
                      id={`${id}-coex`}
                      className="mt-0.5"
                    />
                    <Label
                      htmlFor={`${id}-coex`}
                      className="flex-col items-start gap-0.5 font-normal"
                    >
                      <span className="font-medium">
                        WhatsApp Business + ChatNexus
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Continue usando o WhatsApp Business no celular enquanto
                        o ChatNexus processa as conversas.
                      </span>
                    </Label>
                  </div>
                </RadioGroup>
                {wabaModo === "coexistence" && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    O número precisa atender aos requisitos atuais da Meta para
                    WhatsApp Business Coexistence. Quando você responder pelo
                    celular, a IA para naquela conversa até alguém clicar em
                    &quot;Devolver à IA&quot;.
                  </p>
                )}
                <div className="mt-3">
                  <WabaOAuthButton
                    modo={wabaModo}
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


        </div>
      </div>
    </div>
  );
}
