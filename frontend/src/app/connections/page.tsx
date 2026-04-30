import { Smartphone } from "lucide-react";

import { getConexoes } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ConexaoList } from "./conexao-list";

export const dynamic = "force-dynamic";

/**
 * Página /connections — gestão de linhas WhatsApp (Twilio sandbox/prod, WABA).
 *
 * Exibe as conexões da empresa ativa, permite criar/editar/desativar.
 * O webhook usa essa lista pra resolver empresa + agente por número
 * de destino.
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

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar as conexões</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <ConexaoList conexoes={conexoes} />}
    </div>
  );
}
