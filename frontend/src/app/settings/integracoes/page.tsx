import { Plug } from "lucide-react";

import {
  type ApiConnection,
  getGoogleCalendarConfig,
  getWarelineConfig,
  listApiConnections,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ApiConnectionsSection } from "./api-connections-section";
import { GoogleCalendarCard } from "./google-calendar-card";
import { WarelineCard } from "./wareline-card";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{
    google_calendar?: string;
    google_calendar_error?: string;
  }>;
}

/**
 * Página /settings/integracoes — integrações externas da empresa ativa.
 *
 * - Google Calendar (M5.a): OAuth pra agendamento via Google
 * - Wareline ConecteHub (Sprint Wareline): consulta agenda + criar
 *   marcação no sistema do hospital
 * - Conexões de API genéricas (Sprint Conector API): catálogo com Asaas
 *   + provider custom (Bearer/Basic/API Key) cadastrável via UI
 */
export default async function IntegracoesPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;

  let googleConfig: Awaited<ReturnType<typeof getGoogleCalendarConfig>> = null;
  let warelineConfig: Awaited<ReturnType<typeof getWarelineConfig>> = null;
  let apiConnections: ApiConnection[] = [];
  let loadError: string | null = null;

  try {
    const [g, w, api] = await Promise.all([
      getGoogleCalendarConfig().catch(() => null),
      getWarelineConfig().catch(() => null),
      listApiConnections().catch(() => ({ items: [] })),
    ]);
    googleConfig = g;
    warelineConfig = w;
    apiConnections = api.items;
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

      <GoogleCalendarCard config={googleConfig} />
      <WarelineCard initialConfig={warelineConfig} />
      <ApiConnectionsSection initialConnections={apiConnections} />
    </div>
  );
}
