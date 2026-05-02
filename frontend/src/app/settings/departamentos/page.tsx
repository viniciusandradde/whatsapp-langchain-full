import { Building } from "lucide-react";

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
    const data = await getDepartamentos();
    departamentos = data.departamentos;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro ao carregar departamentos.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Building className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Departamentos</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Categorize atendimentos pra direcionar pra equipe certa
            (suporte, vendas, financeiro…).
          </p>
        </div>
      </div>

      <DepartamentosList
        initialDepartamentos={departamentos}
        loadError={error}
      />
    </div>
  );
}
