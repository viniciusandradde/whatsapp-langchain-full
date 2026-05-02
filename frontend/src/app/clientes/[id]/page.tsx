import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { getCliente } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ClienteDetailClient } from "./cliente-detail-client";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

/**
 * Página /clientes/[id] — ficha completa de um cliente.
 *
 * Dados base (nome, telefone, etc) ficam read-only nesta versão; tags
 * e anotações são editáveis pelo client component abaixo.
 */
export default async function ClienteDetailPage({ params }: PageProps) {
  await requireSession();
  const { id: rawId } = await params;
  const clienteId = Number(rawId);
  if (!Number.isFinite(clienteId) || clienteId <= 0) notFound();

  let detail: Awaited<ReturnType<typeof getCliente>> | null = null;
  let error: string | null = null;

  try {
    detail = await getCliente(clienteId);
  } catch (e) {
    if (e instanceof Error && e.message.includes("404")) notFound();
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao carregar cliente.";
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link
          href="/clientes"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      </div>
    );
  }

  if (!detail) notFound();
  const { cliente, anotacoes } = detail;

  return (
    <div className="space-y-6">
      <Link
        href="/clientes"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar para clientes
      </Link>

      <div>
        <h1 className="text-2xl font-semibold">{cliente.nome ?? cliente.telefone}</h1>
        <p className="mt-0.5 font-mono text-sm text-muted-foreground">
          {cliente.telefone}
        </p>
      </div>

      <Card>
        <CardContent className="grid grid-cols-1 gap-3 py-5 sm:grid-cols-2">
          <Field label="E-mail" value={cliente.email} />
          <Field label="Documento" value={cliente.doc} />
          <Field label="Status" value={cliente.status} />
          <Field
            label="Cadastrado em"
            value={new Date(cliente.created_at).toLocaleString("pt-BR")}
          />
        </CardContent>
      </Card>

      <ClienteDetailClient
        clienteId={cliente.id}
        initialTags={cliente.tags}
        anotacoes={anotacoes}
      />
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-sm">{value ?? "—"}</span>
    </div>
  );
}
