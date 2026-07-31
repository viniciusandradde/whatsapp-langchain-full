import { ShieldOff } from "lucide-react";

import { PageHeader } from "@/components/page-header";
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
      {/* "Whitelist" diz o contrário do que a tela faz: número listado aqui
          é BLOQUEADO de receber resposta automática. O nome vem da tabela
          (`whitelist_numero`, mig 133) e nunca deveria ter chegado na tela. */}
      <PageHeader
        titulo="Números sem IA"
        descricao="Quem está nesta lista nunca recebe resposta automática, em nenhuma conexão — a mensagem continua chegando na fila para uma pessoa atender."
        icon={ShieldOff}
      />
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
      <WhitelistAdmin initialItems={items} />
    </div>
  );
}
