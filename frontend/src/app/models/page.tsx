import { Brain } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import { getAgentConfig, getAgents, getModels } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AgentConfigForm } from "./agent-config-form";

export const dynamic = "force-dynamic";

/**
 * Página /models — escolha do modelo LLM por agente.
 *
 * Server Component que busca em paralelo a lista de agentes e a lista
 * curada de modelos, depois resolve a config atual de cada agente. Cada
 * agente vira um Card com 2 selects (principal + multimodal) e botão Salvar.
 * O override fica no DB (tabela agent_llm_config) com hot reload — a
 * próxima mensagem já usa o modelo novo.
 */
export default async function ModelsPage() {
  await requireSession();

  let agents: string[] = [];
  let modelsList: Awaited<ReturnType<typeof getModels>>["models"] = [];
  let configs: Awaited<ReturnType<typeof getAgentConfig>>[] = [];
  let error: string | null = null;

  try {
    const [agentsResp, modelsResp] = await Promise.all([
      getAgents(),
      getModels(),
    ]);
    agents = agentsResp.agents;
    modelsList = modelsResp.models;
    configs = await Promise.all(agents.map((id) => getAgentConfig(id)));
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro desconhecido ao buscar dados.";
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Modelo por agente"
        descricao="Escolha qual modelo cada agente usa para conversar e qual usa para entender imagem e áudio."
        icon={Brain}
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar a configuração</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && configs.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <Brain className="mx-auto h-10 w-10 mb-3 opacity-50" />
          <p className="font-medium">Nenhum agente registrado</p>
        </div>
      )}

      {configs.length > 0 && (
        <div className="space-y-4">
          {configs.map((config) => (
            <AgentConfigForm
              key={config.agent_id}
              config={config}
              models={modelsList}
            />
          ))}
        </div>
      )}
    </div>
  );
}
