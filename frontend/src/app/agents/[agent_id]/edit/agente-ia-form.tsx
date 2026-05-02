"use client";

import { useState, useTransition } from "react";
import { RotateCcw, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AgenteIAConfig } from "@/lib/api";

import {
  resetAgenteIAConfigAction,
  saveAgenteIAConfigAction,
} from "./actions";

interface Props {
  agentId: string;
  config: AgenteIAConfig | null;
  defaultPrompt: string;
}

export function AgenteIAForm({ agentId, config, defaultPrompt }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isPending, startTransition] = useTransition();

  const initialPrompt = config?.system_prompt_override ?? "";
  const initialTemp = config?.temperatura ?? "";
  const initialAtivo = config?.ativo ?? true;
  const isOverride = !!config && !!config.system_prompt_override && config.ativo;

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    const form = new FormData(e.currentTarget);
    startTransition(async () => {
      const r = await saveAgenteIAConfigAction(agentId, form);
      if (!r.ok) setError(r.error);
      else setSuccess(true);
    });
  }

  function handleReset() {
    if (
      !confirm(
        "Voltar ao prompt padrão do catálogo? Suas customizações serão removidas."
      )
    )
      return;
    setError(null);
    setSuccess(false);
    startTransition(async () => {
      const r = await resetAgenteIAConfigAction(agentId);
      if (!r.ok) setError(r.error);
      else setSuccess(true);
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Configuração da IA</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Personalize o comportamento do agente para esta empresa.
            </p>
          </div>
          {isOverride && (
            <Badge variant="default">override ativo</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="system_prompt_override"
              className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
            >
              System Prompt (override)
            </label>
            <textarea
              id="system_prompt_override"
              name="system_prompt_override"
              defaultValue={initialPrompt}
              placeholder={
                "Vazio = usa o prompt padrão do catálogo (mostrado abaixo)."
              }
              rows={14}
              maxLength={20000}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Vazio mantém o comportamento default. Mantenha as instruções
              técnicas (formatação, idioma, etc) que o agente precisa.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="temperatura"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Temperatura{" "}
                <span className="normal-case">(0 = preciso, 2 = criativo)</span>
              </label>
              <input
                id="temperatura"
                name="temperatura"
                type="number"
                step="0.1"
                min={0}
                max={2}
                defaultValue={initialTemp}
                placeholder="(default do provider)"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input
                type="checkbox"
                name="ativo"
                defaultChecked={initialAtivo}
                className="size-4"
              />
              Override ativo
            </label>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {success && (
            <p className="text-sm text-emerald-300">Salvo.</p>
          )}

          <div className="flex justify-end gap-2">
            {config && (
              <Button
                type="button"
                variant="ghost"
                onClick={handleReset}
                disabled={isPending}
              >
                <RotateCcw className="size-3.5" />
                Voltar ao default
              </Button>
            )}
            <Button type="submit" disabled={isPending}>
              <Save className="size-3.5" />
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>

        <details className="mt-6">
          <summary className="cursor-pointer text-xs uppercase tracking-wide text-muted-foreground">
            Prompt padrão do catálogo (referência)
          </summary>
          <pre className="mt-2 overflow-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
            {defaultPrompt}
          </pre>
        </details>
      </CardContent>
    </Card>
  );
}
