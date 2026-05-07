import Link from "next/link";
import { Headphones } from "lucide-react";

import {
  getAtendimentos,
  getDepartamentos,
  type Departamento,
  type TipoVisualizacao,
} from "@/lib/api";
import { requireSession } from "@/lib/session";
import { cn } from "@/lib/utils";

import { AtendimentoList } from "./atendimento-list";
import { ListFilters } from "./list-filters";

export const dynamic = "force-dynamic";

const TABS: { tipo: TipoVisualizacao; label: string }[] = [
  { tipo: "meus", label: "Meus" },
  { tipo: "aguardando", label: "Aguardando" },
  { tipo: "grupos", label: "Grupos" },
  { tipo: "outros", label: "Outros" },
];

type Prioridade = "baixa" | "media" | "alta" | "urgente";

interface PageProps {
  searchParams: Promise<{
    tipo?: string;
    dep_id?: string;
    prioridade?: string;
    q?: string;
  }>;
}

function isValidTipo(value: string | undefined): value is TipoVisualizacao {
  return (
    value === "meus" ||
    value === "aguardando" ||
    value === "grupos" ||
    value === "outros"
  );
}

function isValidPrioridade(v: string | undefined): v is Prioridade {
  return v === "baixa" || v === "media" || v === "alta" || v === "urgente";
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
  const depId = sp.dep_id ? Number(sp.dep_id) : undefined;
  const prioridade = isValidPrioridade(sp.prioridade) ? sp.prioridade : undefined;
  const q = sp.q?.trim() || undefined;

  let atendimentos: Awaited<
    ReturnType<typeof getAtendimentos>
  >["atendimentos"] = [];
  let departamentos: Departamento[] = [];
  let error: string | null = null;

  try {
    const [data, deps] = await Promise.all([
      getAtendimentos({ tipo, depId, prioridade, q }),
      getDepartamentos().catch(() => ({ departamentos: [] })),
    ]);
    atendimentos = data.atendimentos;
    departamentos = deps.departamentos;
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

      <ListFilters
        tipo={tipo}
        departamentos={departamentos}
        depId={depId}
        prioridade={prioridade}
        q={q}
      />

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
