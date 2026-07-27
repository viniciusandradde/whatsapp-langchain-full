"use server";

import { revalidatePath } from "next/cache";

import { setTracesProvider, type ObsProvider } from "@/lib/api";
import { ApiRequestError, friendlyError } from "@/lib/api-error-shared";
import { requireSession } from "@/lib/session";

/**
 * Troca o provider de observabilidade (Langfuse / LangSmith / automático).
 *
 * A preferência vive em `app_setting` (mig 141), não em env: assim desligar o
 * stack do Langfuse não exige redeploy pra `/traces` voltar a funcionar.
 */
export async function setTracesProviderAction(
  provider: ObsProvider
): Promise<{ ok: true } | { ok: false; error: string }> {
  await requireSession();
  try {
    await setTracesProvider(provider);
    revalidatePath("/traces");
    return { ok: true };
  } catch (e) {
    // Detalhe técnico (status/rota) só no log do servidor; a UI recebe frase
    // amigável em pt-BR.
    console.error("[traces] troca de provider", e);
    if (e instanceof ApiRequestError) {
      return { ok: false, error: friendlyError(e.status, String(e.detail ?? "")) };
    }
    return { ok: false, error: "Não foi possível trocar a fonte de traces." };
  }
}
