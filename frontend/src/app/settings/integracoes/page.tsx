import { Plug } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import {
  type ApiConnection,
  type AsaasConfigStatus,
  getAsaasConfig,
  getGoogleCalendarConfig,
  isMyAdmin,
  listApiConnections,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ApiConnectionsSection } from "./api-connections-section";
import { AsaasCard } from "./asaas-card";

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
 *   marcação no sistema do hospital
 * - Conexões de API genéricas (Sprint Conector API): provider custom
 *   (Bearer/Basic/API Key) cadastrável via UI
 *
 * NÃO inclui: Asaas (gerenciado em /billing — integração GLOBAL do SaaS).
 */
export default async function IntegracoesPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;

  let googleConfig: Awaited<ReturnType<typeof getGoogleCalendarConfig>> = null;
  let apiConnections: ApiConnection[] = [];
  let loadError: string | null = null;

  try {
    const [g, api] = await Promise.all([
      getGoogleCalendarConfig().catch(() => null),
      listApiConnections().catch(() => ({ items: [] })),
    ]);
    googleConfig = g;
    apiConnections = api.items;
  } catch (e) {
    loadError =
      e instanceof Error ? e.message : "Erro desconhecido ao carregar config.";
  }

  // Asaas é config GLOBAL da plataforma — só superadmin vê/edita.
  let isSuper = false;
  let asaasConfig: AsaasConfigStatus | null = null;
  const me = await isMyAdmin().catch(() => ({ is_superadmin: false }));
  isSuper = me.is_superadmin;
  if (isSuper) {
    asaasConfig = await getAsaasConfig().catch(() => null);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Integrações externas"
        icon={Plug}
      />

      {sp.google_calendar === "ok" && (
        <div className="rounded-lg border border-success/40 bg-success/10 p-4 text-sm text-success">
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

      {isSuper && asaasConfig && <AsaasCard initialConfig={asaasConfig} />}
      <ApiConnectionsSection
        initialConnections={apiConnections}
        googleCalendarConfig={googleConfig}
      />
    </div>
  );
}
