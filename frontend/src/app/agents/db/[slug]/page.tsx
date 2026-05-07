import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { getAgenteIA, getModelosLLM, type ModeloLLM } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AgenteEditor } from "./agente-editor";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ slug: string }>;
}

export default async function AgenteDbEditPage({ params }: Props) {
  await requireSession();
  const { slug } = await params;

  let agente;
  let error: string | null = null;
  try {
    agente = await getAgenteIA(slug);
  } catch (e) {
    if (e instanceof Error && e.message.includes("404")) notFound();
    error = e instanceof Error ? e.message : "Erro ao carregar agente.";
  }

  // Modelos LLM (chat) — opcional, fallback pra lista vazia se falhar
  let modelosChat: ModeloLLM[] = [];
  try {
    const r = await getModelosLLM({ tipo: "chat", onlyActive: true });
    modelosChat = r.items;
  } catch {
    // Sem modelos? Editor cai pra input text livre.
  }

  if (!agente && !error) notFound();

  return (
    <div className="space-y-6">
      <Link
        href="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar para agentes
      </Link>

      {error ? (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : (
        <AgenteEditor initialAgente={agente!} modelosChat={modelosChat} />
      )}
    </div>
  );
}
