import { Flag } from "lucide-react";

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
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Flag className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Feature flags</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Liga/desliga features experimentais por empresa sem redeploy.
            Cache TTL 60s — invalida automático no save.
          </p>
        </div>
      </div>

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
