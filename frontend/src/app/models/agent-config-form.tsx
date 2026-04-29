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
import type { AgentLLMConfig, ModelInfo } from "@/lib/api";

import { saveAgentConfig } from "./actions";

interface AgentConfigFormProps {
  config: AgentLLMConfig;
  models: ModelInfo[];
}

const SELECT_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm " +
  "ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring " +
  "focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Form de seleção de modelo principal e multimodal pra um agente.
 *
 * Cada select tem opção "Padrão (.env)" no topo (value=""), que limpa o
 * override no DB. As demais opções vêm de `CURATED_MODELS` filtradas pelo
 * tipo correspondente.
 */
export function AgentConfigForm({ config, models }: AgentConfigFormProps) {
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  const chatModels = models.filter((m) => m.type === "chat");
  const mediaModels = models.filter((m) => m.type === "media");

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    startTransition(async () => {
      const result = await saveAgentConfig(config.agent_id, formData);
      setFeedback(result.ok ? { kind: "ok" } : { kind: "err", message: result.error });
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-base">{config.agent_id}</CardTitle>
        <CardDescription>
          Modelo atual: <span className="font-mono">{config.chat_model}</span>
          {" · "}
          Multimodal: <span className="font-mono">{config.midia_model}</span>
        </CardDescription>
      </CardHeader>
      <form action={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor={`chat_model_${config.agent_id}`}
              className="text-sm font-medium"
            >
              Modelo principal
            </label>
            <select
              id={`chat_model_${config.agent_id}`}
              name="chat_model"
              defaultValue={config.chat_model_override ?? ""}
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="">Padrão (.env)</option>
              {chatModels.map((m) => (
                <option key={`chat-${m.id}`} value={m.id}>
                  {m.label} — {m.id}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor={`midia_model_${config.agent_id}`}
              className="text-sm font-medium"
            >
              Modelo multimodal (imagem/áudio)
            </label>
            <select
              id={`midia_model_${config.agent_id}`}
              name="midia_model"
              defaultValue={config.midia_model_override ?? ""}
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="">Padrão (.env)</option>
              {mediaModels.map((m) => (
                <option key={`media-${m.id}`} value={m.id}>
                  {m.label} — {m.id}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
        <CardFooter className="flex items-center justify-between">
          <div aria-live="polite" className="text-sm">
            {feedback?.kind === "ok" && (
              <span className="text-green-600">Salvo. Próxima mensagem usa o novo modelo.</span>
            )}
            {feedback?.kind === "err" && (
              <span className="text-destructive">Erro: {feedback.message}</span>
            )}
          </div>
          <Button type="submit" disabled={isPending}>
            {isPending ? "Salvando..." : "Salvar"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
