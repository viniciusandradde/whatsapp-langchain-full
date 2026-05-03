"use client";

import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Conexao, ConexaoProvider, TestEvolutionResult } from "@/lib/api";

import { saveConexao, testEvolutionAction } from "./actions";

interface Props {
  initial?: Conexao;
  onDone?: () => void;
}

const SELECT_CLASS =
  "w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "ring-offset-background focus:outline-none focus:ring-2 focus:ring-brand-primary/30 " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const INPUT_CLASS =
  "w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

/**
 * Form de criar/editar conexão WhatsApp.
 *
 * Quando `initial` está presente, virá pre-preenchido e dispara PUT;
 * caso contrário, POST.
 */
export function ConexaoForm({ initial, onDone }: Props) {
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  // Re-render quando o usuário troca o provider para mostrar campos
  // específicos (Evolution: instance_name + url + key + botão de teste).
  const [provider, setProvider] = useState<ConexaoProvider>(
    initial?.provider ?? "twilio_sandbox"
  );

  // Estado do botão "Testar conexão" (provider=evolution apenas).
  const [evoApiUrl, setEvoApiUrl] = useState("");
  const [evoApiKey, setEvoApiKey] = useState("");
  const [evoInstance, setEvoInstance] = useState(
    String((initial?.payload_json?.instance_name as string | undefined) ?? "")
  );
  const [isTesting, startTesting] = useTransition();
  const [testResult, setTestResult] = useState<TestEvolutionResult | null>(null);

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    startTransition(async () => {
      const result = await saveConexao(initial?.id ?? null, formData);
      if (result.ok) {
        setFeedback({ kind: "ok" });
        onDone?.();
      } else {
        setFeedback({ kind: "err", message: result.error });
      }
    });
  }

  function handleTestEvolution() {
    setTestResult(null);
    startTesting(async () => {
      const r = await testEvolutionAction({
        api_url: evoApiUrl,
        api_key: evoApiKey,
        instance_name: evoInstance,
      });
      setTestResult(r);
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {initial ? "Editar conexão" : "Nova conexão"}
        </CardTitle>
        <CardDescription>
          O `from_number` é único globalmente — o webhook usa ele pra
          resolver empresa + agente.
        </CardDescription>
      </CardHeader>
      <form action={handleSubmit}>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Provider" htmlFor="provider">
            <select
              id="provider"
              name="provider"
              value={provider}
              onChange={(e) =>
                setProvider(e.target.value as ConexaoProvider)
              }
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="twilio_sandbox">Twilio Sandbox</option>
              <option value="twilio_prod">Twilio Production</option>
              <option value="waba">WhatsApp Business (WABA)</option>
              <option value="evolution">Evolution API (não-oficial)</option>
            </select>
          </Field>

          <Field label="Status" htmlFor="status">
            <select
              id="status"
              name="status"
              defaultValue={initial?.status ?? "active"}
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="active">Active</option>
              <option value="disabled">Disabled</option>
              <option value="error">Error</option>
            </select>
          </Field>

          <Field label="From number (E.164)" htmlFor="from_number">
            <input
              id="from_number"
              name="from_number"
              required
              defaultValue={initial?.from_number ?? ""}
              placeholder="+14155238886"
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          <Field label="Display name" htmlFor="display_name">
            <input
              id="display_name"
              name="display_name"
              defaultValue={initial?.display_name ?? ""}
              placeholder="Linha comercial"
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          <Field label="Account SID (Twilio)" htmlFor="sid">
            <input
              id="sid"
              name="sid"
              defaultValue={initial?.sid ?? ""}
              placeholder="ACxxxxxxxx"
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          <Field label="Default agent" htmlFor="default_agent_id">
            <input
              id="default_agent_id"
              name="default_agent_id"
              defaultValue={initial?.default_agent_id ?? "vsa_tech"}
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              name="is_default"
              defaultChecked={initial?.is_default ?? false}
              disabled={isPending}
              className="size-4 rounded border-white/20 bg-obsidian-800"
            />
            Conexão default (usada quando empresa não cita conexão específica)
          </label>

          {provider === "evolution" && (
            <div className="md:col-span-2 space-y-3 rounded-md border border-white/10 bg-obsidian-900/50 p-4">
              <div className="text-sm font-medium">Evolution API</div>
              <p className="text-xs text-muted-foreground">
                Multi-instância: cada conexão aponta pra uma `instance_name`
                cadastrada no servidor Evolution. Use o botão abaixo pra
                validar antes de salvar.
              </p>

              <Field label="Instance name" htmlFor="instance_name">
                <input
                  id="instance_name"
                  name="instance_name"
                  required
                  value={evoInstance}
                  onChange={(e) => setEvoInstance(e.target.value)}
                  placeholder="vsa-tecnologia"
                  className={INPUT_CLASS}
                  disabled={isPending}
                />
              </Field>

              <Field label="API URL (apenas para teste)" htmlFor="evo_api_url">
                <input
                  id="evo_api_url"
                  value={evoApiUrl}
                  onChange={(e) => setEvoApiUrl(e.target.value)}
                  placeholder="https://evolutionapi.exemplo.com.br"
                  className={INPUT_CLASS}
                  disabled={isPending || isTesting}
                />
              </Field>

              <Field label="API key (apenas para teste)" htmlFor="evo_api_key">
                <input
                  id="evo_api_key"
                  type="password"
                  value={evoApiKey}
                  onChange={(e) => setEvoApiKey(e.target.value)}
                  placeholder="6B46C86D..."
                  className={INPUT_CLASS}
                  disabled={isPending || isTesting}
                />
              </Field>

              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleTestEvolution}
                  disabled={
                    isPending ||
                    isTesting ||
                    !evoApiUrl ||
                    !evoApiKey ||
                    !evoInstance
                  }
                >
                  {isTesting ? "Testando…" : "Testar conexão"}
                </Button>
                <div className="text-xs" aria-live="polite">
                  {testResult?.ok && (
                    <span className="text-green-500">
                      OK — instância `{testResult.instance_name}` em estado
                      `{testResult.state}`.
                    </span>
                  )}
                  {testResult && !testResult.ok && (
                    <span className="text-destructive">
                      {testResult.error}
                    </span>
                  )}
                </div>
              </div>

              <p className="text-xs text-muted-foreground">
                URL e API key não são salvos na conexão — vêm do `.env` do
                servidor (`EVOLUTION_API_URL`, `EVOLUTION_API_KEY`). O
                campo `instance_name` é gravado em `payload_json`.
              </p>
            </div>
          )}
        </CardContent>
        <CardFooter className="flex items-center justify-between">
          <div aria-live="polite" className="text-sm">
            {feedback?.kind === "ok" && (
              <span className="text-green-500">Salvo.</span>
            )}
            {feedback?.kind === "err" && (
              <span className="text-destructive">{feedback.message}</span>
            )}
          </div>
          <Button type="submit" disabled={isPending}>
            {isPending ? "Salvando…" : initial ? "Atualizar" : "Criar"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}
