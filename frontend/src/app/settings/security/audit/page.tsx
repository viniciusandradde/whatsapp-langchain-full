import { ScrollText } from "lucide-react";

import { PageHeader } from "@/components/page-header";

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
      <PageHeader
        titulo="Registro de auditoria"
        descricao="Tudo que foi alterado no sistema, por quem e quando. O registro não pode ser apagado nem editado — é o que a LGPD exige."
        icon={ScrollText}
      />

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
