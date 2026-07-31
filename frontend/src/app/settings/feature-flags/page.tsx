import { Flag } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { getFeatureFlags } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { FlagsList } from "./flags-list";

export const dynamic = "force-dynamic";

export default async function FeatureFlagsPage() {
  await requireSession();

  let items: Awaited<ReturnType<typeof getFeatureFlags>>["items"] = [];
  let error: string | null = null;
  try {
    const r = await getFeatureFlags();
    items = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar flags.";
  }

  return (
    <div className="space-y-6">
      {/* "Cache TTL 60s — invalida automático no save" era nota de
          implementação na tela do cliente. Sai; o que importa é que demora
          até um minuto pra valer. */}
      <PageHeader
        titulo="Recursos ativados"
        descricao="Liga e desliga recursos em teste nesta empresa. A mudança vale em até um minuto, sem precisar de atualização do sistema."
        icon={Flag}
      />

      {error ? (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : (
        <FlagsList initialFlags={items} />
      )}
    </div>
  );
}
