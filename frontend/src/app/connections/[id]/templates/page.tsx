import { notFound } from "next/navigation";
import { ChevronLeft, FileCheck } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { getConexao, listTemplates } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { TemplatesList } from "./templates-list";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function TemplatesPage({ params }: PageProps) {
  await requireSession();
  const { id } = await params;
  const conexaoId = parseInt(id, 10);
  if (isNaN(conexaoId)) notFound();

  let conexao;
  let templates;
  let error: string | null = null;

  try {
    conexao = await getConexao(conexaoId);
    const t = await listTemplates(conexaoId);
    templates = t.templates;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar templates.";
  }

  if (conexao && conexao.provider !== "waba") {
    return (
      <div className="space-y-4">
        <Link href="/connections" className="text-sm text-muted-foreground hover:underline">
          ← Voltar pra conexões
        </Link>
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
          Templates HSM são exclusivos de conexões WhatsApp Oficial (WABA).
          Esta conexão usa provider <code>{conexao.provider}</code>.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/connections"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-muted/30"
        >
          <ChevronLeft className="h-4 w-4" />
        </Link>
        <FileCheck className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">
          Templates HSM —{" "}
          <span className="text-muted-foreground font-normal text-lg">
            {conexao?.display_name || conexao?.from_number}
          </span>
        </h1>
      </div>

      <p className="text-sm text-muted-foreground -mt-3">
        Templates aprovados pela Meta. Necessários pra mandar mensagem fora
        da janela de 24h após a última msg do cliente.
      </p>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {!error && conexao && (
        <TemplatesList
          conexaoId={conexaoId}
          initialTemplates={templates || []}
        />
      )}
    </div>
  );
}
