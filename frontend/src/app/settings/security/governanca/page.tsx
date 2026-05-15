import { Shield } from "lucide-react";

import { getMyEmpresas, listAuditGovernanca } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { GovernancaList } from "./governanca-list";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{
    actor_user_id?: string;
    target_user_id?: string;
    action?: string;
    offset?: string;
  }>;
}

/**
 * /settings/security/governanca — viewer de audit_governanca (Sprint
 * Governança RBAC). Lista mudanças de perfis/departamentos/role
 * cronologicamente. Útil pra compliance LGPD (rastreabilidade de quem
 * mudou permissão de quem).
 *
 * Filtra por empresa default do user (admin de várias empresas: troca
 * via /companies). Endpoint backend valida membership.
 */
export default async function GovernancaAuditPage({ searchParams }: Props) {
  await requireSession();
  const params = await searchParams;
  const limit = 100;
  const offset = Number(params.offset ?? "0");

  let empresaId: number | null = null;
  let items: Awaited<ReturnType<typeof listAuditGovernanca>>["items"] = [];
  let error: string | null = null;

  try {
    const empresas = await getMyEmpresas();
    // Pega primeira empresa do user (admin pode trocar via /companies)
    const def = empresas.empresas[0];
    if (!def) {
      error = "Você não tem empresas vinculadas.";
    } else {
      empresaId = def.id;
      const r = await listAuditGovernanca(def.id, {
        actor_user_id: params.actor_user_id,
        target_user_id: params.target_user_id,
        action: params.action,
        limit,
        offset,
      });
      items = r.items;
    }
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar audit governança.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Shield className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Governança — Audit</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Registro imutável de mudanças de RBAC: atribuição de perfis,
            departamentos, roles e status de membros. Compliance LGPD.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {!error && empresaId !== null && (
        <GovernancaList
          items={items}
          limit={limit}
          offset={offset}
          filters={params}
        />
      )}
    </div>
  );
}
