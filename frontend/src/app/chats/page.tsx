import { History } from "lucide-react";

import { ApiError } from "@/components/ui/api-error";
import { EmptyState } from "@/components/ui/empty-state";
import {
  getConexoes,
  getDepartamentos,
  getHistorico,
  getTags,
  type HistoricoFiltrosParams,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { HistoricoFilters } from "./historico-filters";
import { HistoricoTable } from "./historico-table";

export const dynamic = "force-dynamic";

type SP = Record<string, string | string[] | undefined>;

function str(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

function arr(v: string | string[] | undefined): string[] | undefined {
  if (v === undefined) return undefined;
  return Array.isArray(v) ? v : [v];
}

/**
 * Histórico de Atendimentos (aba "Conversas"). Substitui a listagem legada:
 * consulta sobre TODOS os status com período + filtros + paginação + detalhe +
 * export CSV/Excel. Backend: GET /api/historico.
 */
export default async function ConversasPage({
  searchParams,
}: {
  searchParams: Promise<SP>;
}) {
  await requireSession();
  const sp = await searchParams;

  const page = Math.max(1, Number(str(sp.page)) || 1);
  const limit = Math.min(200, Math.max(10, Number(str(sp.limit)) || 50));

  const filtros: HistoricoFiltrosParams = {
    createdDe: str(sp.created_de),
    createdAte: str(sp.created_ate),
    status: arr(sp.status),
    conexaoId: str(sp.conexao_id) ? Number(str(sp.conexao_id)) : undefined,
    departamentoId: str(sp.departamento_id)
      ? Number(str(sp.departamento_id))
      : undefined,
    tagId: str(sp.tag_id) ? Number(str(sp.tag_id)) : undefined,
    prioridade: str(sp.prioridade),
    q: str(sp.q),
    sortField: str(sp.sort_field) || "created_at",
    sortOrder: (str(sp.sort_order) as "asc" | "desc") || "desc",
    page,
    limit,
  };

  let data: Awaited<ReturnType<typeof getHistorico>> | null = null;
  let deptos: { id: number; nome: string }[] = [];
  let conexoes: { id: number; label: string }[] = [];
  let tags: { id: number; nome: string; cor: string | null }[] = [];
  let error: string | null = null;

  try {
    const [hist, dep, con, tg] = await Promise.all([
      getHistorico(filtros),
      getDepartamentos().catch(() => ({ departamentos: [] })),
      getConexoes().catch(() => ({ conexoes: [] })),
      getTags(true).catch(() => ({ items: [] })),
    ]);
    data = hist;
    deptos = (dep.departamentos ?? []).map((d) => ({ id: d.id, nome: d.nome }));
    conexoes = (con.conexoes ?? []).map((c) => ({
      id: c.id,
      label: c.display_name || c.from_number || `Conexão ${c.id}`,
    }));
    tags = (tg.items ?? []).map((t) => ({ id: t.id, nome: t.nome, cor: t.cor }));
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar histórico.";
  }

  return (
    <div className="space-y-5">
      <header className="flex items-center gap-3">
        <History className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-xl font-semibold">Histórico de Atendimentos</h1>
          <p className="text-sm text-muted-foreground">
            Consulte, filtre e exporte todas as conversas — abertas e
            finalizadas.
          </p>
        </div>
      </header>

      <HistoricoFilters
        deptos={deptos}
        conexoes={conexoes}
        tags={tags}
        current={sp}
      />

      {error && <ApiError error={error} />}

      {!error && data && data.rows.length === 0 && (
        <EmptyState
          icon={History}
          title="Nenhum atendimento encontrado"
          description="Ajuste o período ou os filtros para ver o histórico."
        />
      )}

      {!error && data && data.rows.length > 0 && (
        <HistoricoTable
          rows={data.rows}
          total={data.total}
          page={data.page}
          limit={data.limit}
          current={sp}
        />
      )}
    </div>
  );
}
