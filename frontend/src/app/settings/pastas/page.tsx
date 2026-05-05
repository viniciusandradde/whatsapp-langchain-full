import { FolderTree } from "lucide-react";

import { getPastas } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { PastasList } from "./pastas-list";

export const dynamic = "force-dynamic";

/**
 * Página /settings/pastas — organização hierárquica da base de
 * conhecimento (E2.C M7).
 *
 * Pasta é container puramente UI/governança — não afeta o ranking
 * RAG. O agente continua buscando em todos os documentos ativos da
 * empresa via `search_knowledge_base`.
 */
export default async function PastasPage() {
  await requireSession();

  let pastas: Awaited<ReturnType<typeof getPastas>>["items"] = [];
  let error: string | null = null;
  try {
    const data = await getPastas({ comDocs: true });
    pastas = data.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar pastas.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <FolderTree className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">
            Pastas da base de conhecimento
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Estrutura em árvore pra organizar documentos. Não afeta o
            ranking de busca — apenas categoriza.
          </p>
        </div>
      </div>

      <PastasList initialPastas={pastas} loadError={error} />
    </div>
  );
}
