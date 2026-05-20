"use client";

import { useState } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

import { createConexaoAction } from "./actions";

interface Props {
  onClose: (refresh: boolean) => void;
}

export function TwilioFormModal({ onClose }: Props) {
  const [provider, setProvider] = useState<"twilio_sandbox" | "twilio_prod">(
    "twilio_sandbox"
  );
  const [displayName, setDisplayName] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [sid, setSid] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const r = await createConexaoAction({
      provider,
      from_number: fromNumber.trim(),
      display_name: displayName.trim() || null,
      sid: sid.trim() || null,
      is_default: isDefault,
      status: "active",
    });
    setBusy(false);
    if (r.ok) onClose(true);
    else setError(r.error);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border/40 bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 className="text-lg font-semibold">Conexão Twilio</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Tipo
            </label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as never)}
              className="h-9 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
            >
              <option value="twilio_sandbox">Sandbox (dev)</option>
              <option value="twilio_prod">Produção</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Nome
            </label>
            <input className={inputCls}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Ex: Suporte"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Número (E.164) *
            </label>
            <input className={inputCls}
              value={fromNumber}
              onChange={(e) => setFromNumber(e.target.value)}
              placeholder="+14155238886"
              required
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Número Twilio (Sandbox usa +14155238886 default).
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              SID (opcional)
            </label>
            <input className={inputCls}
              value={sid}
              onChange={(e) => setSid(e.target.value)}
              placeholder="AC..."
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
            />
            Conexão padrão pra outbound
          </label>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose(false)}
              disabled={busy}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={busy}>
              {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Criar conexão
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
