"use client";

import { useState, useTransition } from "react";
import { ArrowLeft, ExternalLink, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ProviderFieldSpec, ProviderSpec } from "@/lib/api";

import { createApiConnectionAction } from "./actions";

interface Props {
  providers: ProviderSpec[];
  onClose: (refreshed: boolean) => void;
  /** Callback especial pro provider google_calendar (dispara OAuth Web). */
  onGoogleConnect?: () => void;
}

/**
 * Modal 2 steps:
 * 1) Pick provider (lista cards)
 * 2) Form dinâmico baseado em provider.campos
 *
 * Provider especial google_calendar: pulamos o form e disparamos OAuth Web.
 */
export function NewConnectionModal({
  providers,
  onClose,
  onGoogleConnect,
}: Props) {
  const [step, setStep] = useState<"pick" | "form">("pick");
  const [selected, setSelected] = useState<ProviderSpec | null>(null);
  const [label, setLabel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const pickProvider = (p: ProviderSpec) => {
    // Google Calendar: OAuth Web flow especial — não tem form
    if (p.slug === "google_calendar" && onGoogleConnect) {
      onGoogleConnect();
      return;
    }
    setSelected(p);
    setLabel(p.nome);
    setBaseUrl(p.base_url_default ?? "");
    // Pre-fill defaults
    const defaults: Record<string, string> = {};
    for (const f of p.campos) {
      if (f.default) defaults[f.name] = f.default;
    }
    setCredentials(defaults);
    setStep("form");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    setError(null);
    setSubmitting(true);
    startTransition(async () => {
      const r = await createApiConnectionAction({
        provider_slug: selected.slug,
        label: label.trim(),
        credentials,
        base_url: baseUrl || undefined,
      });
      setSubmitting(false);
      if (r.ok) {
        onClose(true);
      } else {
        setError(r.error);
      }
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-2xl rounded-lg border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b p-4">
          <div className="flex items-center gap-2">
            {step === "form" && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                onClick={() => setStep("pick")}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
            )}
            <h2 className="text-lg font-semibold">
              {step === "pick"
                ? "Escolha o tipo de integração"
                : `Nova conexão · ${selected?.nome}`}
            </h2>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {step === "pick" ? (
          <div className="max-h-[60vh] overflow-y-auto p-4">
            {(() => {
              // Wareline tem card próprio acima — esconde do picker
              const visible = providers.filter((p) => p.slug !== "wareline");
              if (visible.length === 0) {
                return (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    Nenhum provider disponível.
                  </p>
                );
              }
              return (
                <ul className="grid gap-2 sm:grid-cols-2">
                  {visible.map((p) => (
                  <li key={p.slug}>
                    <button
                      type="button"
                      onClick={() => pickProvider(p)}
                      className="flex h-full w-full flex-col items-start gap-1 rounded-md border bg-background p-3 text-left transition-colors hover:border-brand-primary hover:bg-muted/30"
                    >
                      <span className="font-medium">{p.nome}</span>
                      <span className="text-xs text-muted-foreground">
                        {p.descricao}
                      </span>
                      {p.docs_url && (
                        <a
                          href={p.docs_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-flex items-center gap-1 text-[10px] text-brand-primary hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Docs
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      )}
                    </button>
                  </li>
                ))}
                </ul>
              );
            })()}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="max-h-[70vh] overflow-y-auto">
            <div className="space-y-4 p-4">
              <div>
                <label className="mb-1 block text-xs font-medium">
                  Nome da conexão (label) *
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  required
                  maxLength={80}
                  placeholder="Ex: Asaas Produção"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  Usado pra distinguir múltiplas conexões do mesmo provider
                </p>
              </div>

              {selected?.base_url_default !== undefined && (
                <div>
                  <label className="mb-1 block text-xs font-medium">
                    Base URL
                  </label>
                  <input
                    type="url"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder={selected.base_url_default ?? ""}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
                  />
                </div>
              )}

              {selected?.campos.map((field) => (
                <DynamicField
                  key={field.name}
                  field={field}
                  value={credentials[field.name] ?? ""}
                  onChange={(v) =>
                    setCredentials((prev) => ({ ...prev, [field.name]: v }))
                  }
                />
              ))}

              {error && (
                <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                  {error}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t p-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => onClose(false)}
                disabled={submitting}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Conectar
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function DynamicField({
  field,
  value,
  onChange,
}: {
  field: ProviderFieldSpec;
  value: string;
  onChange: (v: string) => void;
}) {
  const required = field.required;
  return (
    <div>
      <label className="mb-1 block text-xs font-medium">
        {field.label} {required && <span className="text-destructive">*</span>}
      </label>
      {field.type === "select" && field.options ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : field.type === "textarea" ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          placeholder={field.placeholder ?? ""}
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
        />
      ) : (
        <input
          type={
            field.type === "password"
              ? "password"
              : field.type === "url"
                ? "url"
                : field.type === "number"
                  ? "number"
                  : "text"
          }
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          placeholder={field.placeholder ?? ""}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-brand-primary"
        />
      )}
      {field.help_text && (
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          {field.help_text}
        </p>
      )}
    </div>
  );
}
