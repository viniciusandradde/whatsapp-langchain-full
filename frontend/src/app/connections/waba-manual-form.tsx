"use client";

import { useId, useState, useTransition } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { wabaManualAction } from "./actions";

/**
 * Conexão manual da API oficial — ID do número + ID da conta + token, como a
 * "configuração manual" do Chatwoot. Para número que já está ativo na Cloud
 * API (o número de teste da Meta, ou um número que o cliente já usa na API).
 * O token precisa ser de um usuário do sistema com acesso ao App do ChatNexus.
 */
export function WabaManualForm({ onSuccess }: { onSuccess: () => void }) {
  const id = useId();
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [token, setToken] = useState("");
  const [nome, setNome] = useState("");
  const [appProprio, setAppProprio] = useState(false);
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const soDigitos = (v: string) => v.replace(/\D/g, "");
  const pronto =
    phoneId.length >= 5 &&
    wabaId.length >= 5 &&
    token.trim().length >= 20 &&
    (!appProprio || appSecret.trim().length >= 16);

  return (
    <form
      className="mt-3 space-y-3 rounded-md border border-border/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!pronto) return;
        startTransition(async () => {
          setErro(null);
          const r = await wabaManualAction({
            phone_number_id: phoneId,
            waba_account_id: wabaId,
            access_token: token.trim(),
            display_name: nome.trim() || null,
            app_secret: appProprio ? appSecret.trim() : null,
            app_id: appProprio && appId ? appId : null,
          });
          if (r.ok) {
            setToken("");
            setAppSecret("");
            onSuccess();
          } else {
            setErro(r.error);
          }
        });
      }}
    >
      <p className="text-xs text-muted-foreground">
        Para número que já está ativo na API oficial da Meta. Os dados ficam na
        tela Configuração da API do App da Meta. Use um token de usuário do
        sistema, com validade &quot;Nunca&quot;.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor={`${id}-phone`}>ID do número de telefone</Label>
          <Input
            id={`${id}-phone`}
            inputMode="numeric"
            autoComplete="off"
            value={phoneId}
            onChange={(e) => setPhoneId(soDigitos(e.target.value))}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${id}-waba`}>ID da conta do WhatsApp Business</Label>
          <Input
            id={`${id}-waba`}
            inputMode="numeric"
            autoComplete="off"
            value={wabaId}
            onChange={(e) => setWabaId(soDigitos(e.target.value))}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${id}-token`}>Token de acesso</Label>
        <Input
          id={`${id}-token`}
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Fica guardado protegido e não aparece de novo na tela.
        </p>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${id}-nome`}>Nome da conexão (opcional)</Label>
        <Input
          id={`${id}-nome`}
          value={nome}
          maxLength={80}
          onChange={(e) => setNome(e.target.value)}
        />
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={appProprio}
          onChange={(e) => setAppProprio(e.target.checked)}
        />
        <span>
          Usar o App da Meta da própria empresa
          <span className="block text-xs text-muted-foreground">
            Depois de conectar, a página da conexão mostra o endereço e o token
            para colar no webhook do seu App.
          </span>
        </span>
      </label>
      {appProprio && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor={`${id}-appid`}>ID do App (opcional)</Label>
            <Input
              id={`${id}-appid`}
              inputMode="numeric"
              autoComplete="off"
              value={appId}
              onChange={(e) => setAppId(soDigitos(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-secret`}>Chave secreta do App</Label>
            <Input
              id={`${id}-secret`}
              type="password"
              autoComplete="off"
              value={appSecret}
              onChange={(e) => setAppSecret(e.target.value)}
            />
          </div>
        </div>
      )}
      {erro && <p className="text-xs text-destructive">{erro}</p>}
      <Button type="submit" size="sm" disabled={!pronto || pending} className="gap-2">
        {pending && <Loader2 className="h-4 w-4 animate-spin" />}
        Conectar
      </Button>
    </form>
  );
}
