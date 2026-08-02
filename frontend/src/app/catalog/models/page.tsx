import { Brain, Plus } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/components/ui/api-error";
import { ButtonLink } from "@/components/ui/button";
import { getModelosLLM } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ModelosTabela } from "./modelos-tabela";

export const dynamic = "force-dynamic";

/**
 * /catalog/models — o cardápio de modelos que os agentes desta empresa podem
 * usar. Junta os globais (curados por nós) com os que a empresa cadastrou.
 *
 * Não confundir com `/models`, que escolhe qual modelo cada agente usa. Aqui é
 * o cardápio; lá é o pedido.
 */
export default async function CatalogModelsPage() {
  await requireSession();

  let items: Awaited<ReturnType<typeof getModelosLLM>>["items"] = [];
  let error: unknown = null;
  try {
    const r = await getModelosLLM({ onlyActive: false });
    items = r.items;
  } catch (e) {
    error = e;
  }

  return (
    <div>
      <PageHeader
        titulo="Catálogo de modelos"
        descricao="Compare custo, janela de contexto e capacidade antes de escolher o modelo de um agente."
        icon={Brain}
        acoes={
          <ButtonLink href="/catalog/models/new">
            <Plus className="size-4" />
            Novo modelo
          </ButtonLink>
        }
      />

      {error ? (
        <ApiError error={error} variant="card" />
      ) : (
        <ModelosTabela itens={items} />
      )}
    </div>
  );
}
