import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Bot } from "lucide-react";

import { getAgenteIAConfig, getAgents } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AgenteIAForm } from "./agente-ia-form";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ agent_id: string }>;
}

/**
 * Página /agents/[agent_id]/edit — editor da configuração IA do agente.
 *
 * Mostra o prompt padrão do catálogo + form pra override por empresa.
 * Usuários da empresa ativa podem reescrever instruções, ajustar
 * temperatura e desativar/reativar o override sem mexer em código.
 */
export default async function EditAgentePage({ params }: PageProps) {
  await requireSession();
  const { agent_id: agentId } = await params;

  // Valida se o agente existe no catálogo (404 cedo).
  try {
    const data = await getAgents();
    if (!data.agents.includes(agentId)) notFound();
  } catch {
    // API indisponível — deixa o getAgenteIAConfig levantar adiante.
  }

  let config: Awaited<ReturnType<typeof getAgenteIAConfig>> | null = null;
  let error: string | null = null;
  try {
    config = await getAgenteIAConfig(agentId);
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro ao carregar configuração.";
  }

  return (
    <div className="space-y-6">
      <Link
        href="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar para agentes
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Bot className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">{agentId}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Editar comportamento da IA para a empresa ativa.
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {config && (
        <AgenteIAForm
          agentId={agentId}
          config={config.config}
          defaultPrompt={config.default_system_prompt}
        />
      )}
    </div>
  );
}
