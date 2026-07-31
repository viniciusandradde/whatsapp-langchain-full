import { Building } from "lucide-react";

import { PageHeader } from "@/components/page-header";

import { getDepartamentos } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { DepartamentosList } from "./departamentos-list";

export const dynamic = "force-dynamic";

export default async function DepartamentosPage() {
  await requireSession();

  let departamentos: Awaited<
    ReturnType<typeof getDepartamentos>
  >["departamentos"] = [];
  let error: string | null = null;
  try {
    const data = await getDepartamentos({ comUsers: true });
    departamentos = data.departamentos;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro ao carregar departamentos.";
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Departamentos"
        descricao="Categorize atendimentos pra direcionar pra equipe certa (suporte, vendas, financeiro…)."
        icon={Building}
      />

      <DepartamentosList
        initialDepartamentos={departamentos}
        loadError={error}
      />
    </div>
  );
}
