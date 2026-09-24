"use client";

import { useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WabaWebhookInfo } from "@/lib/api";

function Copiavel({ rotulo, valor, oculto }: { rotulo: string; valor: string; oculto?: boolean }) {
  const [copiado, setCopiado] = useState(false);
  const [visivel, setVisivel] = useState(!oculto);
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {rotulo}
      </div>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-border/60 bg-muted/30 px-2 py-1.5 text-xs">
          {visivel ? valor : "•".repeat(Math.min(valor.length, 24))}
        </code>
        {oculto && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0"
            aria-label={visivel ? "Ocultar" : "Mostrar"}
            onClick={() => setVisivel((v) => !v)}
          >
            {visivel ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1"
          onClick={async () => {
            await navigator.clipboard.writeText(valor);
            setCopiado(true);
            setTimeout(() => setCopiado(false), 1500);
          }}
        >
          {copiado ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copiado ? "Copiado" : "Copiar"}
        </Button>
      </div>
    </div>
  );
}

/**
 * Webhook da conexão que usa o App da Meta da própria empresa (ADR-006): a
 * empresa cola o endereço e o token no App dela e assina os campos listados.
 */
export function WebhookConexao({ info }: { info: WabaWebhookInfo }) {
  if (!info.app_proprio || !info.verify_token) return null;
  return (
    <div className="space-y-3 rounded-lg border border-border/40 p-4">
      <div>
        <h2 className="text-sm font-semibold">Webhook do seu App da Meta</h2>
        <p className="text-xs text-muted-foreground">
          No painel da Meta, abra o seu App → WhatsApp → Configuração, cole o
          endereço e o token abaixo, clique em &quot;Verificar e salvar&quot; e assine os
          campos listados.
        </p>
      </div>
      <Copiavel rotulo="URL de callback" valor={info.url} />
      <Copiavel rotulo="Token de verificação" valor={info.verify_token} oculto />
      <div className="text-xs text-muted-foreground">
        Campos para assinar:{" "}
        {info.campos.map((c, i) => (
          <span key={c}>
            <code>{c}</code>
            {i < info.campos.length - 1 ? ", " : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
