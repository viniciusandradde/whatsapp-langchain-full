"use client";

import { useState } from "react";
import { Check, Copy, KeyRound, ShieldCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  password: string;
  userName: string;
  onClose: () => void;
}

export function SenhaGeradaModal({ password, userName, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback antigo
      const ta = document.createElement("textarea");
      ta.value = password;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-xl border border-amber-500/30 bg-obsidian-900 shadow-2xl">
        <div className="flex items-start justify-between border-b border-foreground/10 p-4">
          <div className="flex items-center gap-2">
            <KeyRound className="size-5 text-amber-400" />
            <h2 className="text-lg font-semibold">Senha gerada</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          <p className="text-sm text-muted-foreground">
            Senha temporária pra <span className="font-medium text-foreground">{userName}</span>:
          </p>

          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 font-mono text-base tracking-wide text-amber-200">
              {password}
            </code>
            <Button
              size="icon"
              variant="outline"
              onClick={handleCopy}
              title="Copiar senha"
            >
              {copied ? <Check className="size-4 text-emerald-500" /> : <Copy className="size-4" />}
            </Button>
          </div>

          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-amber-400" />
            <div className="text-xs text-amber-200/90 space-y-1">
              <p className="font-medium">Esta senha aparece UMA vez.</p>
              <p>
                Copie agora e envie pelo WhatsApp ou canal seguro. Não será
                possível visualizar de novo — use &ldquo;Resetar senha&rdquo;
                se precisar.
              </p>
            </div>
          </div>
        </div>

        <div className="flex justify-end border-t border-foreground/10 p-4">
          <Button onClick={onClose}>Entendi, já copiei</Button>
        </div>
      </div>
    </div>
  );
}
