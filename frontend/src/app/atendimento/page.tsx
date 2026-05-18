import { Headphones } from "lucide-react";

import {
  getAtendimentos,
  getContadoresAtendimento,
  getDepartamentos,
  getMyAbas,
  type Aba,
  type ContadoresAtendimento,
  type Departamento,
  type TipoVisualizacao,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { AtendimentoList } from "./atendimento-list";
import { AtendimentoSidebar } from "./atendimento-sidebar";
import { ListFilters } from "./list-filters";

export const dynamic = "force-dynamic";

type Prioridade = "baixa" | "media" | "alta" | "urgente";

interface PageProps {
  searchParams: Promise<{
    tipo?: string;
    dep_id?: string;
    prioridade?: string;
    q?: string;
    aba_id?: string;
    // Multi-valor — Next entrega como string[] ou string
    tag_id?: string | string[];
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
 * Página /atendimento — layout 2 colunas (sidebar + lista).
 *
 * Sidebar (Sprint Atendimento UX) tem 2 seções:
 *  - Sistema: Aguardando / Meus / Outros (status-derived, contadores)
 *  - Minhas Abas: pastas customizáveis pelo user logado (mig 085)
 *
 * Quando `?aba_id=` está presente, a lista mostra só atendimentos
 * pinneados naquela aba do user — sobrepondo o `?tipo=` system.
 */
export default async function AtendimentoPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;
  const abaId = sp.aba_id ? Number(sp.aba_id) : undefined;
  // Quando aba está selecionada, mostramos todos os status abertos
  // ("aguardando" + "em_andamento") via tipo="outros" no backend.
  const tipoBase: TipoVisualizacao = isValidTipo(sp.tipo) ? sp.tipo : "aguardando";
  const tipo: TipoVisualizacao = abaId ? "outros" : tipoBase;
  const depId = sp.dep_id ? Number(sp.dep_id) : undefined;
  const prioridade = isValidPrioridade(sp.prioridade) ? sp.prioridade : undefined;
  const q = sp.q?.trim() || undefined;
  const tagIds = (
    Array.isArray(sp.tag_id) ? sp.tag_id : sp.tag_id ? [sp.tag_id] : []
  )
    .map(Number)
    .filter((n) => Number.isFinite(n) && n > 0);

  let atendimentos: Awaited<
    ReturnType<typeof getAtendimentos>
  >["atendimentos"] = [];
  let departamentos: Departamento[] = [];
  let abas: Aba[] = [];
  let contadores: ContadoresAtendimento | null = null;
  let error: string | null = null;

  try {
    const [data, deps, myAbas, conts] = await Promise.all([
      getAtendimentos({ tipo, depId, prioridade, q, abaId, tagIds }),
      getDepartamentos().catch(() => ({ departamentos: [] })),
      getMyAbas().catch(() => ({ items: [] })),
      getContadoresAtendimento().catch(() => null),
    ]);
    atendimentos = data.atendimentos;
    departamentos = deps.departamentos;
    abas = myAbas.items;
    contadores = conts;
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar atendimentos.";
  }

  // Título dinâmico baseado em contexto
  let contextoLabel = "Atendimentos";
  if (abaId) {
    const aba = abas.find((a) => a.id === abaId);
    if (aba) contextoLabel = `Aba: ${aba.descricao}`;
  } else if (tipoBase === "meus") {
    contextoLabel = "Meus atendimentos";
  } else if (tipoBase === "aguardando") {
    contextoLabel = "Aguardando atendimento";
  } else if (tipoBase === "outros") {
    contextoLabel = "Outros atendimentos";
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-0 -m-6">
      <AtendimentoSidebar
        initialAbas={abas}
        initialContadores={contadores}
      />
      <main className="flex flex-1 flex-col overflow-y-auto p-6">
        <div className="mb-6 flex items-center gap-2">
          <Headphones className="h-6 w-6" />
          <h1 className="text-2xl font-semibold">{contextoLabel}</h1>
        </div>

        <ListFilters
          tipo={tipo}
          departamentos={departamentos}
          depId={depId}
          prioridade={prioridade}
          q={q}
          tagIds={tagIds}
        />

        {error && (
          <div className="mt-4 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            <p className="font-medium">Não foi possível carregar a caixa</p>
            <p className="mt-1 text-destructive/80">{error}</p>
          </div>
        )}

        {!error && (
          <div className="mt-4">
            <AtendimentoList atendimentos={atendimentos} tipo={tipo} />
          </div>
        )}
      </main>
    </div>
  );
}
