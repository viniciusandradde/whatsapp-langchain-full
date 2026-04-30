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
import type { Empresa } from "@/lib/api";

import { saveEmpresa } from "./actions";

interface Props {
  initial?: Empresa;
  onDone?: () => void;
}

const INPUT_CLASS =
  "w-full rounded-md border border-white/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

const SELECT_CLASS = INPUT_CLASS;

export function EmpresaForm({ initial, onDone }: Props) {
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    startTransition(async () => {
      const result = await saveEmpresa(initial?.id ?? null, formData);
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
          {initial ? "Editar empresa" : "Nova empresa"}
        </CardTitle>
        <CardDescription>
          O slug é o identificador URL-friendly único globalmente. Quem
          cria vira admin automaticamente.
        </CardDescription>
      </CardHeader>
      <form action={handleSubmit}>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Nome" htmlFor="nome">
            <input
              id="nome"
              name="nome"
              required
              defaultValue={initial?.nome ?? ""}
              placeholder="Acme Inc"
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          <Field label="Slug" htmlFor="slug">
            <input
              id="slug"
              name="slug"
              required
              minLength={2}
              defaultValue={initial?.slug ?? ""}
              placeholder="acme"
              className={`${INPUT_CLASS} font-mono`}
              disabled={isPending}
            />
          </Field>

          <Field label="Plano" htmlFor="plano">
            <select
              id="plano"
              name="plano"
              defaultValue={initial?.plano ?? "free"}
              className={SELECT_CLASS}
              disabled={isPending}
            >
              <option value="free">Free</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </Field>

          <Field label="Documento (CNPJ/CPF)" htmlFor="doc">
            <input
              id="doc"
              name="doc"
              defaultValue={initial?.doc ?? ""}
              placeholder="00.000.000/0000-00"
              className={INPUT_CLASS}
              disabled={isPending}
            />
          </Field>

          {initial && (
            <Field label="Status" htmlFor="status">
              <select
                id="status"
                name="status"
                defaultValue={initial.status}
                className={SELECT_CLASS}
                disabled={isPending}
              >
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="archived">Archived</option>
              </select>
            </Field>
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
