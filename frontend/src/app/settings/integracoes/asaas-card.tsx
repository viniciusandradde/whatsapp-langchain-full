"use client";

import { useState, useTransition } from "react";
import { AlertCircle, CheckCircle2, CreditCard, Globe, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AsaasConfigStatus } from "@/lib/api";

import { saveAsaasConfigAction, testAsaasAction } from "./actions";

interface Props {
  initialConfig: AsaasConfigStatus;
}

/**
 * Card de config GLOBAL da integração Asaas (billing da plataforma).
 *
 * Só renderizado para SUPERADMIN (a página gateia). Asaas é a conta única que
 * fatura as empresas-clientes — não é per-empresa. DB tem precedência sobre env.
 * Campos sensíveis (api_key, webhook_token) em branco MANTÊM o valor anterior.
 */
export function AsaasCard({ initialConfig }: Props) {
  const [cfg, setCfg] = useState<AsaasConfigStatus>(initialConfig);
  const [environment, setEnvironment] = useState(cfg.environment || "sandbox");
  const [apiKey, setApiKey] = useState("");
  const [webhookToken, setWebhookToken] = useState("");
  const [successUrl, setSuccessUrl] = useState(cfg.success_url || "");
  const [cancelUrl, setCancelUrl] = useState(cfg.cancel_url || "");

  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, startSave] = useTransition();
  const [testing, startTest] = useTransition();

  const sensitiveRequired = !cfg.tem_api_key || !cfg.tem_webhook_token;

  function handleSave() {
    setMsg(null);
    startSave(async () => {
      const r = await saveAsaasConfigAction({
        environment,
        api_key: apiKey || undefined,
        webhook_token: webhookToken || undefined,
        success_url: successUrl,
        cancel_url: cancelUrl,
      });
      if (r.ok) {
        setMsg({ ok: true, text: "Configuração salva." });
        setApiKey("");
        setWebhookToken("");
        setCfg({
          ...cfg,
          configurado: true,
          source: "db",
          environment,
          tem_api_key: true,
          tem_webhook_token: true,
          success_url: successUrl,
          cancel_url: cancelUrl,
        });
      } else {
        setMsg({ ok: false, text: r.error });
      }
    });
  }

  function handleTest() {
    setMsg(null);
    startTest(async () => {
      const r = await testAsaasAction();
      setMsg({ ok: r.ok, text: r.mensagem });
    });
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
          <div>
            <h3 className="font-medium">Asaas — Cobrança (plataforma)</h3>
            <p className="text-xs text-muted-foreground">
              Conta única que fatura as empresas-clientes. Global da plataforma —
              só superadmin configura.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {cfg.configurado ? (
            <Badge variant="default" className="gap-1">
              <CheckCircle2 className="h-3 w-3" /> Configurado
            </Badge>
          ) : (
            <Badge variant="secondary">Não configurado</Badge>
          )}
          <Badge variant="outline" className="gap-1">
            <Globe className="h-3 w-3" />
            {cfg.source === "db"
              ? "via UI"
              : cfg.source === "env"
                ? "via env"
                : "—"}
          </Badge>
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        <label className="text-sm">
          Ambiente
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            <option value="sandbox">Sandbox (testes)</option>
            <option value="production">Produção</option>
          </select>
        </label>

        <label className="text-sm">
          Chave de API {cfg.tem_api_key && !sensitiveRequired && "(salva — em branco mantém)"}
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={cfg.tem_api_key ? "••••••••" : "$aact_..."}
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </label>

        <label className="text-sm">
          Token do webhook
          <input
            type="password"
            value={webhookToken}
            onChange={(e) => setWebhookToken(e.target.value)}
            placeholder={cfg.tem_webhook_token ? "••••••••" : "token livre que você define"}
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </label>

        <label className="text-sm">
          URL de sucesso (opcional)
          <input
            type="text"
            value={successUrl}
            onChange={(e) => setSuccessUrl(e.target.value)}
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </label>

        <label className="text-sm">
          URL de cancelamento (opcional)
          <input
            type="text"
            value={cancelUrl}
            onChange={(e) => setCancelUrl(e.target.value)}
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </label>

        <p className="text-xs text-muted-foreground">
          No painel Asaas → Integrações → Webhook, aponte para{" "}
          <code>{"<sua-api>/webhook/asaas"}</code> e use o mesmo Webhook Token no
          campo de autenticação.
        </p>

        {msg && (
          <div
            className={`flex items-center gap-2 text-sm ${
              msg.ok ? "text-green-600" : "text-red-600"
            }`}
          >
            {msg.ok ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <AlertCircle className="h-4 w-4" />
            )}
            {msg.text}
          </div>
        )}

        <div className="flex gap-2">
          <Button
            onClick={handleSave}
            disabled={saving || (sensitiveRequired && (!apiKey || !webhookToken))}
          >
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
          <Button variant="outline" onClick={handleTest} disabled={testing}>
            {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Testar conexão
          </Button>
        </div>
      </div>
    </div>
  );
}
