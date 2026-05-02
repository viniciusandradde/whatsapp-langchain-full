import { Webhook } from "lucide-react";

import { getHookEventos, getHooks } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { HooksList } from "./hooks-list";

export const dynamic = "force-dynamic";

/**
 * Página /hooks — gestão de webhooks configuráveis (M4.d).
 *
 * Cada hook é POST HTTP que dispara quando o evento associado acontece.
 * O dispatcher entrega async (fire-and-forget) e grava cada tentativa
 * em hook_log; a UI permite inspecionar o histórico recente.
 */
export default async function HooksPage() {
  await requireSession();

  let hooks: Awaited<ReturnType<typeof getHooks>>["hooks"] = [];
  let eventos: Awaited<ReturnType<typeof getHookEventos>>["eventos"] = [];
  let error: string | null = null;

  try {
    const [hRes, eRes] = await Promise.all([getHooks(), getHookEventos()]);
    hooks = hRes.hooks;
    eventos = eRes.eventos;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar hooks.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Webhook className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Webhooks</h1>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar os hooks</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <HooksList hooks={hooks} eventos={eventos} />}
    </div>
  );
}
