"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, RefreshCw, Smartphone, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

import {
  evolutionProvisionAction,
  pollStatusAction,
  refreshQRAction,
} from "./actions";

interface Props {
  onClose: (refresh: boolean) => void;
}

type Phase = "form" | "qr" | "connected" | "error";

export function EvolutionQRModal({ onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("form");
  const [displayName, setDisplayName] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [conexaoId, setConexaoId] = useState<number | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState(45);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleProvision() {
    if (!displayName.trim()) {
      setError("Nome da conexão é obrigatório.");
      return;
    }
    setError(null);
    setPhase("qr");
    const r = await evolutionProvisionAction({
      display_name: displayName.trim(),
      instance_name: instanceName.trim() || undefined,
    });
    if (!r.ok) {
      setPhase("error");
      setError(r.error);
      return;
    }
    setConexaoId(r.data.conexao_id);
    setQr(r.data.qr_base64);
    setExpiresIn(r.data.expires_in);
    startPolling(r.data.conexao_id);
  }

  function startPolling(id: number) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      // Conta countdown
      setExpiresIn((s) => {
        if (s <= 1) {
          // refresh QR
          refreshQRAction(id).then((r) => {
            if (r.ok) {
              setQr(r.data.qr_base64);
              setExpiresIn(r.data.expires_in);
            }
          });
          return 45;
        }
        return s - 1;
      });

      // Status check
      const s = await pollStatusAction(id);
      if (s.ok && s.data.is_active) {
        if (pollRef.current) clearInterval(pollRef.current);
        setPhase("connected");
      }
    }, 1000);
  }

  async function handleManualRefresh() {
    if (!conexaoId) return;
    const r = await refreshQRAction(conexaoId);
    if (r.ok) {
      setQr(r.data.qr_base64);
      setExpiresIn(r.data.expires_in);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(phase === "connected")}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border/40 bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 className="text-lg font-semibold">
            {phase === "form" && "Conectar Evolution"}
            {phase === "qr" && "Escanear QR Code"}
            {phase === "connected" && "Conectado!"}
            {phase === "error" && "Erro na conexão"}
          </h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(phase === "connected")}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          {phase === "form" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Nome da conexão *
                </label>
                <input
                  value={displayName}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setDisplayName(e.target.value)
                  }
                  placeholder="Ex: WhatsApp Vendas"
                  maxLength={80}
                  className={inputCls}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Instance name (opcional)
                </label>
                <input
                  value={instanceName}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setInstanceName(e.target.value)
                  }
                  placeholder="Auto-gerado se vazio"
                  maxLength={80}
                  className={inputCls}
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Identificador interno no Evolution server. Gerado automaticamente
                  se você não preencher.
                </p>
              </div>
              {error && (
                <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => onClose(false)}>
                  Cancelar
                </Button>
                <Button onClick={handleProvision}>Provisionar instance</Button>
              </div>
            </>
          )}

          {phase === "qr" && (
            <>
              <p className="text-sm text-muted-foreground">
                Abra o WhatsApp no celular &gt; Menu &gt; Aparelhos conectados &gt;
                Conectar aparelho, e escaneie o código abaixo.
              </p>
              <div className="flex justify-center rounded-lg border border-border/40 bg-white p-4">
                {qr ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={qr.startsWith("data:") ? qr : `data:image/png;base64,${qr}`}
                    alt="QR Code"
                    className="h-64 w-64"
                  />
                ) : (
                  <div className="flex h-64 w-64 items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Expira em {expiresIn}s</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleManualRefresh}
                  className="gap-1.5"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Atualizar QR
                </Button>
              </div>
            </>
          )}

          {phase === "connected" && (
            <div className="flex flex-col items-center gap-3 p-6">
              <div className="rounded-full bg-emerald-500/20 p-4">
                <Check className="h-8 w-8 text-emerald-400" />
              </div>
              <p className="text-center text-sm">
                <strong>Conectado com sucesso!</strong>
                <br />
                <span className="text-muted-foreground">
                  Sua conexão Evolution está ativa.
                </span>
              </p>
              <Button onClick={() => onClose(true)} className="mt-2">
                Concluir
              </Button>
            </div>
          )}

          {phase === "error" && (
            <>
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error || "Erro desconhecido."}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => onClose(false)}>
                  Fechar
                </Button>
                <Button onClick={() => setPhase("form")}>Tentar de novo</Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
