import { ScrollText } from "lucide-react";

import { getAuditLog } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AuditList } from "./audit-list";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{
    entity_type?: string;
    action?: string;
    user_id?: string;
    offset?: string;
  }>;
}

export default async function AuditLogPage({ searchParams }: Props) {
  await requireSession();
  const params = await searchParams;

  const limit = 50;
  const offset = Number(params.offset ?? "0");

  let items: Awaited<ReturnType<typeof getAuditLog>>["items"] = [];
  let error: string | null = null;
  try {
    const r = await getAuditLog({
      entityType: params.entity_type,
      action: params.action,
      userId: params.user_id,
      limit,
      offset,
    });
    items = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar audit log.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <ScrollText className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Audit log</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Registro imutável de mutations sensíveis (LGPD Art. 38). Filtre
            por entidade, ação ou usuário.
          </p>
        </div>
      </div>

      {error ? (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : (
        <AuditList items={items} limit={limit} offset={offset} filters={params} />
      )}
    </div>
  );
}
