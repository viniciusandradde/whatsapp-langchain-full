import Link from "next/link";
import { ArrowLeft, Users } from "lucide-react";

import { getEmpresaMembers, getMyEmpresas } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { MembersList } from "./members-list";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function MembersPage({ params }: PageProps) {
  await requireSession();
  const { id } = await params;
  const empresaId = Number(id);

  let members: Awaited<ReturnType<typeof getEmpresaMembers>> = [];
  let empresaName: string | null = null;
  let error: string | null = null;

  try {
    const [membersList, empresas] = await Promise.all([
      getEmpresaMembers(empresaId),
      getMyEmpresas().then((r) => r.empresas),
    ]);
    members = membersList;
    empresaName = empresas.find((e) => e.id === empresaId)?.nome ?? null;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar membros.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/companies"
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <Users className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">
          Membros{empresaName ? ` — ${empresaName}` : ""}
        </h1>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar membros</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <MembersList empresaId={empresaId} members={members} />}
    </div>
  );
}
