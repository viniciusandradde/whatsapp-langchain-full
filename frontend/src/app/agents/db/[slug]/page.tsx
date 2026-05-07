import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import {
  getAgenteIA,
  getAgenteTemplates,
  getMenus,
  getModelosLLM,
  type AgenteTemplate,
  type MenuChatbot,
  type ModeloLLM,
} from "@/lib/api";
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

  // Menus chatbot ativos — pra dropdown de acao_limite_menu_id (governança custo)
  let menusAtivos: MenuChatbot[] = [];
  try {
    const r = await getMenus({ onlyActive: true });
    menusAtivos = r.items;
  } catch {
    // Sem menus? Dropdown fica desabilitado.
  }

  // Templates do catálogo Python (pra dropdown na tab Identidade)
  let templates: AgenteTemplate[] = [];
  try {
    const r = await getAgenteTemplates();
    templates = r.items;
  } catch {
    // Fallback: editor renderiza só o template atual sem opção de troca
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
        <AgenteEditor
          initialAgente={agente!}
          modelosChat={modelosChat}
          menusAtivos={menusAtivos}
          templates={templates}
        />
      )}
    </div>
  );
}
