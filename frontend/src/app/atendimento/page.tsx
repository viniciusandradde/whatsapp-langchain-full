import Link from "next/link";
import { Headphones } from "lucide-react";

import { getAtendimentos, type TipoVisualizacao } from "@/lib/api";
import { requireSession } from "@/lib/session";
import { cn } from "@/lib/utils";

import { AtendimentoList } from "./atendimento-list";

export const dynamic = "force-dynamic";

const TABS: { tipo: TipoVisualizacao; label: string }[] = [
  { tipo: "meus", label: "Meus" },
  { tipo: "aguardando", label: "Aguardando" },
  { tipo: "grupos", label: "Grupos" },
  { tipo: "outros", label: "Outros" },
];

interface PageProps {
  searchParams: Promise<{ tipo?: string }>;
}

function isValidTipo(value: string | undefined): value is TipoVisualizacao {
  return (
    value === "meus" ||
    value === "aguardando" ||
    value === "grupos" ||
    value === "outros"
  );
}

/**
 * Página /atendimento — fila de atendimentos com 4 caixas.
 *
 * Lista derivada em runtime via `?tipo=`. Cada cliente cadastrado +
 * conexão tem no máximo 1 atendimento aberto; novos inbound abrem ou
 * anexam.
 */
export default async function AtendimentoPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;
  const tipo: TipoVisualizacao = isValidTipo(sp.tipo) ? sp.tipo : "aguardando";

  let atendimentos: Awaited<
    ReturnType<typeof getAtendimentos>
  >["atendimentos"] = [];
  let error: string | null = null;

  try {
    const data = await getAtendimentos({ tipo });
    atendimentos = data.atendimentos;
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar atendimentos.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Headphones className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Atendimentos</h1>
      </div>

      <nav className="flex flex-wrap gap-2 border-b">
        {TABS.map((tab) => (
          <Link
            key={tab.tipo}
            href={`/atendimento?tipo=${tab.tipo}`}
            className={cn(
              "border-b-2 px-3 py-2 text-sm transition-colors",
              tab.tipo === tipo
                ? "border-brand-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar a caixa</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && <AtendimentoList atendimentos={atendimentos} tipo={tipo} />}
    </div>
  );
}
