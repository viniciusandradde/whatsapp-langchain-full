import { FolderTree } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import {
  getDocumentosConhecimento,
  getPastas,
  type DocumentoConhecimento,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { PastasList } from "./pastas-list";

export const dynamic = "force-dynamic";

/**
 * Base de conhecimento — pastas e documentos.
 *
 * Pasta vinculada a um agente vira filtro do RAG: a busca por similaridade
 * passa a considerar só os documentos daquelas pastas. Sem vínculo, o agente
 * busca em tudo que a empresa tem.
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
    <div>
      <PageHeader
        titulo="Base de conhecimento"
        descricao="Organize os documentos em pastas para controlar o que cada agente consulta."
        icon={FolderTree}
      />
      <PastasList
        initialPastas={pastas}
        initialDocumentos={documentos}
        loadError={error}
      />
    </div>
  );
}
