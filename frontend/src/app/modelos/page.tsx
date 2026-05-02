import { MessagesSquare } from "lucide-react";

import { getModelosMensagem } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ModelosList } from "./modelos-list";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ q?: string }>;
}

/**
 * Página /modelos — gestão de respostas reutilizáveis (quick replies).
 *
 * Os modelos aparecem no dropdown do composer do AtendimentoDrawer pra
 * inserir texto com 2 cliques.
 */
export default async function ModelosPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;
  const search = sp.q?.trim() || undefined;

  let modelos: Awaited<ReturnType<typeof getModelosMensagem>>["modelos"] = [];
  let error: string | null = null;

  try {
    const data = await getModelosMensagem(search);
    modelos = data.modelos;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar modelos.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <MessagesSquare className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Modelos de mensagem</h1>
      </div>

      <form className="flex max-w-md gap-2" action="/modelos" method="get">
        <input
          name="q"
          defaultValue={search ?? ""}
          placeholder="Buscar por título, conteúdo ou atalho…"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <button
          type="submit"
          className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Buscar
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar os modelos</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <ModelosList modelos={modelos} />}
    </div>
  );
}
