import { Building2 } from "lucide-react";

import { getMyEmpresas } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { CompaniesList } from "./companies-list";

export const dynamic = "force-dynamic";

/**
 * Página /companies — gestão das empresas (multi-tenant).
 *
 * Quem cria vira admin (criador é adicionado em empresa_membro com
 * role='admin'). Usuários veem só as empresas onde são membros.
 */
export default async function CompaniesPage() {
  await requireSession();

  let empresas: Awaited<ReturnType<typeof getMyEmpresas>>["empresas"] = [];
  let error: string | null = null;

  try {
    const data = await getMyEmpresas();
    empresas = data.empresas;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar empresas.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Building2 className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Empresas</h1>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar empresas</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <CompaniesList empresas={empresas} />}
    </div>
  );
}
