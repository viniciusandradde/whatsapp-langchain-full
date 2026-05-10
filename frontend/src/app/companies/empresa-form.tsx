"use client";

import { useEffect, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Empresa, EmpresaCsatConfig } from "@/lib/api";

import {
  loadEmpresaCsatAction,
  saveEmpresa,
  saveEmpresaCsatAction,
} from "./actions";

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

// Sprint Y — section CSAT/NPS dentro do edit empresa
const DEFAULT_PERGUNTA = "Como você avalia o atendimento que acabou de receber?";
const DEFAULT_AGRADECIMENTO = "Obrigado pelo seu feedback! 😊";

export function CsatConfigSection({ empresaId }: { empresaId: number }) {
  const [config, setConfig] = useState<EmpresaCsatConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, startSaving] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  useEffect(() => {
    setLoading(true);
    loadEmpresaCsatAction(empresaId)
      .then((r) => {
        if (r.ok) setConfig(r.config);
      })
      .finally(() => setLoading(false));
  }, [empresaId]);

  if (loading || config === null) {
    return (
      <Card className="mt-4">
        <CardContent className="py-6 text-sm text-muted-foreground">
          Carregando config NPS…
        </CardContent>
      </Card>
    );
  }

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    const body: EmpresaCsatConfig = {
      csat_ativo: formData.get("csat_ativo") === "on",
      csat_pergunta: String(formData.get("csat_pergunta") || "").trim() || null,
      csat_msg_agradecimento:
        String(formData.get("csat_msg_agradecimento") || "").trim() || null,
      csat_solicita_comentario:
        formData.get("csat_solicita_comentario") === "on",
    };
    startSaving(async () => {
      const r = await saveEmpresaCsatAction(empresaId, body);
      if (r.ok) {
        setConfig(r.config);
        setFeedback({ kind: "ok" });
      } else {
        setFeedback({ kind: "err", message: r.error });
      }
    });
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="text-base">Pesquisa de Satisfação (NPS)</CardTitle>
        <CardDescription>
          Quando ativada, o cliente recebe uma pergunta com nota 0-10 ao
          fim de cada atendimento. Resultados em /dashboard/qualidade.
        </CardDescription>
      </CardHeader>
      <form action={handleSubmit}>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="csat_ativo"
              defaultChecked={config.csat_ativo}
              disabled={saving}
            />
            <span className="font-medium">Ativar pesquisa NPS</span>
          </label>

          <Field label="Pergunta enviada ao cliente" htmlFor="csat_pergunta">
            <textarea
              id="csat_pergunta"
              name="csat_pergunta"
              rows={2}
              defaultValue={config.csat_pergunta ?? ""}
              placeholder={DEFAULT_PERGUNTA}
              className={INPUT_CLASS}
              disabled={saving}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Vazio = usa o texto padrão.
            </p>
          </Field>

          <Field
            label="Mensagem de agradecimento (após nota/comentário)"
            htmlFor="csat_msg_agradecimento"
          >
            <textarea
              id="csat_msg_agradecimento"
              name="csat_msg_agradecimento"
              rows={2}
              defaultValue={config.csat_msg_agradecimento ?? ""}
              placeholder={DEFAULT_AGRADECIMENTO}
              className={INPUT_CLASS}
              disabled={saving}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="csat_solicita_comentario"
              defaultChecked={config.csat_solicita_comentario}
              disabled={saving}
            />
            <span>Pedir comentário textual após a nota (60s pra responder)</span>
          </label>
        </CardContent>
        <CardFooter className="flex items-center justify-between gap-2">
          <div className="text-sm">
            {feedback?.kind === "ok" && (
              <span className="text-green-500">Salvo.</span>
            )}
            {feedback?.kind === "err" && (
              <span className="text-destructive">{feedback.message}</span>
            )}
          </div>
          <Button type="submit" disabled={saving}>
            {saving ? "Salvando…" : "Salvar config NPS"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
