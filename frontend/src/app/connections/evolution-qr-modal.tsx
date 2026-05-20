"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, RefreshCw, Smartphone, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

import {
  createConexaoAction,
  evolutionProvisionAction,
  pollStatusAction,
  refreshQRAction,
  testEvolutionAction,
} from "./actions";

interface Props {
  onClose: (refresh: boolean) => void;
}

type Phase = "mode" | "form" | "manual" | "qr" | "connected" | "error";

export function EvolutionQRModal({ onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("mode");
  const [displayName, setDisplayName] = useState("");
  const [instanceName, setInstanceName] = useState("");
  const [apiUrl, setApiUrl] = useState("https://evolutionapi.vsatecnologia.com.br");
  const [apiKey, setApiKey] = useState("");
  const [fromNumber, setFromNumber] = useState("");
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

  async function handleManualImport() {
    if (!displayName.trim() || !apiUrl.trim() || !apiKey.trim() || !instanceName.trim()) {
      setError("Preencha nome, URL, api key e instance name.");
      return;
    }
    if (!fromNumber.trim()) {
      setError("Número da conexão (E.164) é obrigatório.");
      return;
    }
    setError(null);
    setPhase("qr"); // reusa loading state
    // 1. testa
    const t = await testEvolutionAction({
      api_url: apiUrl.trim(),
      api_key: apiKey.trim(),
      instance_name: instanceName.trim(),
    });
    if (!t.ok) {
      setPhase("manual");
      setError(t.error || "Credenciais inválidas.");
      return;
    }
    // 2. cria Conexao apontando pra instance existente
    const r = await createConexaoAction({
      provider: "evolution",
      from_number: fromNumber.trim(),
      display_name: displayName.trim(),
      default_agent_id: "vsa_tech",
      status: "active",
      is_default: false,
      payload_json: { instance_name: instanceName.trim() },
    });
    if (!r.ok) {
      setPhase("manual");
      setError(r.error);
      return;
    }
    setPhase("connected");
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
            {phase === "mode" && "Conectar Evolution"}
            {phase === "form" && "Provisionar nova instance"}
            {phase === "manual" && "Importar instance existente"}
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
          {phase === "mode" && (
            <>
              <p className="text-sm text-muted-foreground">
                Você quer provisionar uma instance Evolution nova ou
                conectar uma instance que já existe no seu servidor?
              </p>
              <button
                onClick={() => setPhase("manual")}
                className="flex w-full items-start gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-left hover:bg-emerald-500/10"
              >
                <div className="flex-1">
                  <div className="font-medium">Conectar instance existente</div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Cole URL + api-key + instance name de uma instance
                    já rodando. Recomendado se você já tem Evolution server
                    configurado.
                  </p>
                </div>
              </button>
              <button
                onClick={() => setPhase("form")}
                className="flex w-full items-start gap-3 rounded-lg border border-border/40 p-4 text-left hover:bg-muted/20"
              >
                <div className="flex-1">
                  <div className="font-medium">Provisionar nova instance</div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Cria nova instance no Evolution server via API admin.
                    Exige <code>EVOLUTION_GLOBAL_API_KEY</code> setada no env
                    do Nexus (com permissão de admin do server Evolution).
                  </p>
                </div>
              </button>
            </>
          )}

          {phase === "manual" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Nome da conexão *
                </label>
                <input
                  className={inputCls}
                  value={displayName}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setDisplayName(e.target.value)
                  }
                  placeholder="Ex: VSA Tecnologia"
                  maxLength={80}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Número (E.164) *
                </label>
                <input
                  className={inputCls}
                  value={fromNumber}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setFromNumber(e.target.value)
                  }
                  placeholder="+5567984249725"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  API URL *
                </label>
                <input
                  className={inputCls}
                  value={apiUrl}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setApiUrl(e.target.value)
                  }
                  placeholder="https://evolutionapi.vsatecnologia.com.br"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  API Key *
                </label>
                <input
                  type="password"
                  className={inputCls}
                  value={apiKey}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setApiKey(e.target.value)
                  }
                  placeholder="Chave da instance (apikey)"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Instance name *
                </label>
                <input
                  className={inputCls}
                  value={instanceName}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setInstanceName(e.target.value)
                  }
                  placeholder="vsa-tecnologia"
                />
              </div>
              <p className="text-[11px] text-muted-foreground">
                Antes de salvar, o backend chama o Evolution server pra
                validar que a instance existe e está conectada (state ∈ open/connecting).
              </p>
              {error && (
                <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setPhase("mode")}>
                  Voltar
                </Button>
                <Button onClick={handleManualImport}>Testar e salvar</Button>
              </div>
            </>
          )}

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
