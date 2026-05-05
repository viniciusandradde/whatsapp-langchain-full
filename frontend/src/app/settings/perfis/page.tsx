import { ShieldCheck } from "lucide-react";

import { getPerfis, getPermissoesCatalogo } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { PerfisList } from "./perfis-list";

export const dynamic = "force-dynamic";

/**
 * Página /settings/perfis — RBAC granular (E2.A).
 *
 * Lista perfis (system + custom) + catálogo de permissões. Editor inline
 * permite criar/editar perfil custom e configurar permissões por módulo.
 *
 * Permissão exigida: `perfil.read` (todos os perfis system têm isso na
 * categoria Admin/Gestor; Operador/Leitura não veem essa página).
 */
export default async function PerfisPage() {
  await requireSession();

  let perfis: Awaited<ReturnType<typeof getPerfis>> = { items: [] };
  let catalogo: Awaited<ReturnType<typeof getPermissoesCatalogo>> = { items: [] };
  let loadError: string | null = null;

  try {
    [perfis, catalogo] = await Promise.all([
      getPerfis(),
      getPermissoesCatalogo(),
    ]);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Erro ao carregar perfis.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Perfis de acesso (RBAC)</h1>
      </div>

      {loadError ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {loadError}
        </div>
      ) : (
        <PerfisList perfis={perfis.items} catalogo={catalogo.items} />
      )}
    </div>
  );
}
