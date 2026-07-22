import { ShieldOff } from "lucide-react";

import { getWhitelist, type WhitelistNumero } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { WhitelistAdmin } from "./whitelist-admin";

export const dynamic = "force-dynamic";

export default async function WhitelistPage() {
  await requireSession();

  let items: WhitelistNumero[] = [];
  let error: string | null = null;
  try {
    const r = await getWhitelist();
    items = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar a whitelist.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ShieldOff className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Whitelist de números</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Números que não recebem respostas automáticas da IA em nenhuma conexão
        (ex.: contatos pessoais). As mensagens continuam registradas na fila de
        atendimento — só a resposta automática é desligada.
      </p>
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
      <WhitelistAdmin initialItems={items} />
    </div>
  );
}
