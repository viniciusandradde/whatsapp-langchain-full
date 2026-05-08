import { FolderTree } from "lucide-react";

import {
  getDocumentosConhecimento,
  getPastas,
  type DocumentoConhecimento,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { PastasList } from "./pastas-list";

export const dynamic = "force-dynamic";

/**
 * Página /settings/pastas — organização hierárquica da base de
 * conhecimento (E2.C M7) + gestão de documentos por pasta (Sprint M.6).
 *
 * Sprint M: pastas afetam ranking RAG quando o agente_ia tem
 * `base_conhecimento_ids` configurado — vira filtro WHERE pasta_id IN (...)
 * no cosine search.
 */
export default async function PastasPage() {
  await requireSession();

  let pastas: Awaited<ReturnType<typeof getPastas>>["items"] = [];
  let documentos: DocumentoConhecimento[] = [];
  let error: string | null = null;
  try {
    const [pastasResp, docsResp] = await Promise.all([
      getPastas({ comDocs: true }),
      getDocumentosConhecimento({}),
    ]);
    pastas = pastasResp.items;
    documentos = docsResp.documentos;
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
            Cada pasta vira filtro RAG quando vinculada a um agente_ia.
            Adicione documentos diretamente nas pastas pra restringir o
            que cada setor enxerga.
          </p>
        </div>
      </div>

      <PastasList
        initialPastas={pastas}
        initialDocumentos={documentos}
        loadError={error}
      />
    </div>
  );
}
