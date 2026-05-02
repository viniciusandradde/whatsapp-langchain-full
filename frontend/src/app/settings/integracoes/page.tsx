import { Plug } from "lucide-react";

import { getGoogleCalendarConfig } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { GoogleCalendarCard } from "./google-calendar-card";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ google_calendar?: string; google_calendar_error?: string }>;
}

/**
 * Página /settings/integracoes — integrações externas da empresa ativa.
 *
 * Hoje só tem Google Calendar (M5.a). Hooks ficam em /hooks por serem
 * gerenciamento mais frequente; integrações são auth single-shot.
 */
export default async function IntegracoesPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;

  let config: Awaited<ReturnType<typeof getGoogleCalendarConfig>> = null;
  let loadError: string | null = null;

  try {
    config = await getGoogleCalendarConfig();
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Erro desconhecido ao carregar config.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Plug className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Integrações</h1>
      </div>

      {sp.google_calendar === "ok" && (
        <div className="rounded-lg border border-emerald-500/50 bg-emerald-500/10 p-4 text-sm text-emerald-300">
          Google Calendar conectado com sucesso.
        </div>
      )}
      {sp.google_calendar_error === "user_denied" && (
        <div className="rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4 text-sm text-yellow-300">
          Autorização cancelada no Google. Pode tentar de novo.
        </div>
      )}

      {loadError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {loadError}
        </div>
      )}

      <GoogleCalendarCard config={config} />
    </div>
  );
}
