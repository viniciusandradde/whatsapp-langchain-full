import { Braces } from "lucide-react";

import { getVariaveis } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { VariaveisList } from "./variaveis-list";

export const dynamic = "force-dynamic";

/**
 * Página /settings/variaveis — KVs por empresa pra render em prompts/modelos.
 *
 * Cada variável tem `nome` (chave referenciada como `{{var.NOME}}`) e
 * `valor` (texto que substitui no render). Loader e composer aplicam
 * `render_template` automaticamente antes do texto sair pra Twilio ou
 * virar prompt do agente.
 */
export default async function VariaveisPage() {
  await requireSession();

  let variaveis: Awaited<ReturnType<typeof getVariaveis>>["variaveis"] = [];
  let error: string | null = null;
  try {
    const data = await getVariaveis();
    variaveis = data.variaveis;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro ao carregar variáveis.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Braces className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Variáveis de Ambiente</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            KVs referenciados em prompts e modelos como{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              {"{{var.NOME}}"}
            </code>
            .
          </p>
        </div>
      </div>

      <VariaveisList initialVariaveis={variaveis} loadError={error} />
    </div>
  );
}
