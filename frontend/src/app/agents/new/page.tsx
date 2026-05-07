import Link from "next/link";
import { ArrowLeft, Bot } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAgenteTemplates, type AgenteTemplate } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { createAgenteAction } from "./actions";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function NewAgentePage({ searchParams }: PageProps) {
  await requireSession();
  const params = await searchParams;
  const errorMsg = params.error ?? null;

  // Lista templates disponíveis no catálogo Python (vsa_tech, atendimento_completo, ...)
  let templates: AgenteTemplate[] = [];
  try {
    const r = await getAgenteTemplates();
    templates = r.items;
  } catch {
    // Fallback: hard-coded mínimo se API falhar
    templates = [
      { slug: "vsa_tech", label: "VSA Tech (default)", descricao: "" },
    ];
  }

  return (
    <div className="space-y-6">
      <Link
        href="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Bot className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Novo agente</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Cria agente cadastrável (não exige código). Detalhes (prompt, tools,
            modelo) editados depois.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dados básicos</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMsg && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMsg}
            </p>
          )}
          <form action={createAgenteAction} className="space-y-4">
            <div>
              <label
                htmlFor="slug"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Slug (identificador URL — kebab-case)
              </label>
              <input
                id="slug"
                name="slug"
                required
                pattern="^[a-z][a-z0-9_-]{1,60}$"
                placeholder="vendas-sp"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Começa com letra; usar [a-z 0-9 _ -], 2-60 chars. Não muda depois.
              </p>
            </div>

            <div>
              <label
                htmlFor="nome"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Nome
              </label>
              <input
                id="nome"
                name="nome"
                required
                maxLength={120}
                placeholder="Vendas SP"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label
                htmlFor="descricao"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Descrição (opcional)
              </label>
              <textarea
                id="descricao"
                name="descricao"
                maxLength={500}
                rows={3}
                placeholder="Atende leads SP região sudeste, qualifica via CPF/CNPJ"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label
                htmlFor="template_catalog"
                className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
              >
                Template (catálogo)
              </label>
              <select
                id="template_catalog"
                name="template_catalog"
                defaultValue={
                  templates.find((t) => t.slug === "atendimento_completo")
                    ? "atendimento_completo"
                    : (templates[0]?.slug ?? "vsa_tech")
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {templates.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.label}
                  </option>
                ))}
              </select>
              <div className="mt-1 space-y-1">
                {templates.map((t) => (
                  <p key={t.slug} className="text-[11px] text-muted-foreground">
                    <code className="font-mono">{t.slug}</code>: {t.descricao}
                  </p>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Link href="/agents">
                <Button type="button" variant="ghost">
                  Cancelar
                </Button>
              </Link>
              <Button type="submit">Criar agente</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
