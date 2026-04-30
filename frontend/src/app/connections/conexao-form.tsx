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
import type { Conexao } from "@/lib/api";

import { saveConexao } from "./actions";

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
              defaultValue={initial?.provider ?? "twilio_sandbox"}
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="twilio_sandbox">Twilio Sandbox</option>
              <option value="twilio_prod">Twilio Production</option>
              <option value="waba">WhatsApp Business (WABA)</option>
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
