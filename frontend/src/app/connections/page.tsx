import { Smartphone } from "lucide-react";

import { getConexoes } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ConnectionsList } from "./connections-list";

export const dynamic = "force-dynamic";

/**
 * Página /connections — gestão de canais WhatsApp.
 *
 * Suporta 3 providers: WABA (OAuth Embedded Signup), Evolution (auto-provision
 * com QR), Twilio (form manual). Layout padrão ZigChat com filtros + tabela
 * de badges + ações inline.
 */
export default async function ConnectionsPage() {
  await requireSession();

  let conexoes: Awaited<ReturnType<typeof getConexoes>>["conexoes"] = [];
  let error: string | null = null;

  try {
    const data = await getConexoes();
    conexoes = data.conexoes;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar conexões.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Smartphone className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Conexões WhatsApp</h1>
      </div>

      <p className="text-sm text-muted-foreground -mt-3">
        Gerencie os canais WhatsApp da empresa: WhatsApp Oficial (Meta),
        Evolution API e Twilio.
      </p>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar as conexões</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <ConnectionsList initialConexoes={conexoes} />}
    </div>
  );
}
