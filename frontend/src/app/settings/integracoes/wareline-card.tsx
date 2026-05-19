"use client";

import { useState, useTransition } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  PlugZap,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { WarelineConfig } from "@/lib/api";

import {
  deleteWarelineConfigAction,
  saveWarelineConfigAction,
  testWarelineAction,
} from "./actions";

interface Props {
  initialConfig: WarelineConfig | null;
}

/**
 * Card de configuração da integração Wareline ConecteHub.
 *
 * Padrão UX:
 * - Primeira configuração: TODOS os campos obrigatórios
 * - Edição posterior: senha/secret em branco mantém valor anterior
 *   (placeholder mostra "••••••••")
 * - Botão "Testar conexão" faz OAuth real + busca dummy paciente
 * - Badge mostra resultado do último teste
 */
export function WarelineCard({ initialConfig }: Props) {
  const [config, setConfig] = useState<WarelineConfig | null>(initialConfig);
  const isConfigured = config !== null;

  // Form state
  const [username, setUsername] = useState(initialConfig?.username ?? "");
  const [password, setPassword] = useState("");
  const [clientId, setClientId] = useState(initialConfig?.client_id ?? "");
  const [clientSecret, setClientSecret] = useState("");
  const [baseUrl, setBaseUrl] = useState(
    initialConfig?.base_url ?? "https://modulos.conectew.com.br"
  );
  const [pacientesBaseUrl, setPacientesBaseUrl] = useState(
    initialConfig?.pacientes_base_url ?? "https://services.conectew.com.br"
  );
  const [ativo, setAtivo] = useState(initialConfig?.ativo ?? true);

  // UI state
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    mensagem: string;
  } | null>(null);
  const [, startTransition] = useTransition();

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setTestResult(null);
    setSaving(true);

    const payload: Record<string, unknown> = { ativo };
    if (username && username !== initialConfig?.username)
      payload.username = username;
    if (password) payload.password = password;
    if (clientId && clientId !== initialConfig?.client_id)
      payload.client_id = clientId;
    if (clientSecret) payload.client_secret = clientSecret;
    if (baseUrl !== initialConfig?.base_url) payload.base_url = baseUrl;
    if (pacientesBaseUrl !== initialConfig?.pacientes_base_url)
      payload.pacientes_base_url = pacientesBaseUrl;

    // Primeira configuração: força todos os campos
    if (!isConfigured) {
      payload.username = username;
      payload.password = password;
      payload.client_id = clientId;
      payload.client_secret = clientSecret;
      payload.base_url = baseUrl;
      payload.pacientes_base_url = pacientesBaseUrl;
    }

    startTransition(async () => {
      const r = await saveWarelineConfigAction(payload);
      setSaving(false);
      if (r.ok) {
        setConfig(r.config);
        setPassword("");
        setClientSecret("");
      } else {
        setError(r.error);
      }
    });
  };

  const handleTest = () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    startTransition(async () => {
      const r = await testWarelineAction();
      setTesting(false);
      setTestResult({ ok: r.ok, mensagem: r.mensagem });
    });
  };

  const handleDelete = () => {
    if (
      !confirm(
        "Remover credenciais Wareline? O agente Agendamentos vai parar de funcionar."
      )
    )
      return;
    setDeleting(true);
    startTransition(async () => {
      const r = await deleteWarelineConfigAction();
      setDeleting(false);
      if (r.ok) {
        setConfig(null);
        setUsername("");
        setPassword("");
        setClientId("");
        setClientSecret("");
      } else {
        setError(r.error);
      }
    });
  };

  return (
    <div className="rounded-lg border bg-card p-4 md:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-md bg-brand-primary/10 p-2">
          <PlugZap className="h-5 w-5 text-brand-primary" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Wareline ConecteHub</h2>
            {isConfigured && (
              <Badge variant={config!.ativo ? "default" : "secondary"}>
                {config!.ativo ? "Ativo" : "Inativo"}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Integração com sistema de agendamento médico. Usado pelo agente
            <code className="mx-1 rounded bg-muted px-1 text-xs">
              agendamentos
            </code>
            pra consultar agenda, buscar paciente e criar marcação.
          </p>
          {isConfigured && config!.ultimo_teste_at && (
            <p className="mt-1 text-xs text-muted-foreground">
              Último teste:{" "}
              {new Date(config!.ultimo_teste_at).toLocaleString("pt-BR")} ·{" "}
              {config!.ultimo_teste_ok ? (
                <span className="text-emerald-600 dark:text-emerald-400">
                  ✓ OK
                </span>
              ) : (
                <span className="text-destructive">
                  ✗ Falhou: {config!.ultimo_teste_erro}
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      <form onSubmit={handleSave} className="grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs font-medium">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="usuario.api"
            required
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">Senha</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={
              isConfigured ? "••••••••  (deixe em branco pra manter)" : "Senha"
            }
            required={!isConfigured}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">Client ID</label>
          <input
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="client_id_wareline"
            required
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">
            Client Secret
          </label>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={
              isConfigured ? "••••••••  (deixe em branco pra manter)" : "Secret"
            }
            required={!isConfigured}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
        </div>
        <div className="md:col-span-2">
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              URLs avançadas (raramente precisa mudar)
            </summary>
            <div className="mt-2 grid gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium">
                  Base URL (módulos)
                </label>
                <input
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">
                  Base URL (pacientes — pode ser staging)
                </label>
                <input
                  type="url"
                  value={pacientesBaseUrl}
                  onChange={(e) => setPacientesBaseUrl(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
              </div>
            </div>
          </details>
        </div>
        <div className="md:col-span-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={ativo}
              onChange={(e) => setAtivo(e.target.checked)}
            />
            Integração ativa
          </label>
        </div>

        {error && (
          <div className="md:col-span-2 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {testResult && (
          <div
            className={`md:col-span-2 flex items-start gap-2 rounded-md border p-2 text-xs ${
              testResult.ok
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                : "border-destructive/50 bg-destructive/10 text-destructive"
            }`}
          >
            {testResult.ok ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0" />
            )}
            <span>{testResult.mensagem}</span>
          </div>
        )}

        <div className="md:col-span-2 flex flex-wrap justify-end gap-2 pt-2">
          {isConfigured && (
            <Button
              type="button"
              variant="ghost"
              onClick={handleDelete}
              disabled={deleting || saving || testing}
              className="text-destructive hover:text-destructive"
            >
              {deleting ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-1 h-4 w-4" />
              )}
              Remover
            </Button>
          )}
          {isConfigured && (
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={testing || saving || deleting}
            >
              {testing && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Testar conexão
            </Button>
          )}
          <Button type="submit" disabled={saving || testing || deleting}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {isConfigured ? "Salvar alterações" : "Conectar"}
          </Button>
        </div>
      </form>
    </div>
  );
}
