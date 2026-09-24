import Link from "next/link";
import { Download, UsersRound } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ESTAGIOS_FUNIL, TEMPERATURAS } from "@/lib/lead";

import { ChipsLead } from "./classificacao-lead";
import { ImportarCsvDialog } from "./importar-csv-dialog";
import { NovoClienteDialog } from "./novo-cliente-dialog";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getClientes } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ q?: string; estagio?: string; temperatura?: string }>;
}

const SELECT =
  "h-10 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

/**
 * Página /clientes — diretório dos clientes da empresa ativa.
 *
 * Cada cliente é único por (empresa_id, telefone). Os cards levam à
 * ficha (/clientes/[id]) onde estão anotações e tags.
 */
export default async function ClientesPage({ searchParams }: PageProps) {
  await requireSession();
  const sp = await searchParams;
  const search = sp.q?.trim() || undefined;
  const estagio = ESTAGIOS_FUNIL.some((e) => e.valor === sp.estagio) ? sp.estagio : undefined;
  const temperatura = TEMPERATURAS.some((t) => t.valor === sp.temperatura)
    ? sp.temperatura
    : undefined;
  const filtrando = !!(search || estagio || temperatura);
  const exportarQs = new URLSearchParams();
  if (search) exportarQs.set("search", search);
  if (estagio) exportarQs.set("lifecycle_stage", estagio);
  if (temperatura) exportarQs.set("temperatura", temperatura);

  let clientes: Awaited<ReturnType<typeof getClientes>>["clientes"] = [];
  let error: string | null = null;

  try {
    const data = await getClientes({ search, estagio, temperatura, limit: 50 });
    clientes = data.clientes;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar clientes.";
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Clientes"
        icon={UsersRound}
        acoes={
          <div className="flex flex-wrap gap-2">
            <NovoClienteDialog />
            <ImportarCsvDialog />
            <Button
              variant="outline"
              nativeButton={false}
              render={<a href={`/api/clientes-exportar?${exportarQs.toString()}`} download />}
            >
              <Download className="size-4" />
              Exportar
            </Button>
          </div>
        }
      />

      <form className="flex flex-wrap items-center gap-2" action="/clientes" method="get">
        <input
          name="q"
          defaultValue={search ?? ""}
          placeholder="Buscar por nome, telefone ou e-mail…"
          aria-label="Buscar clientes"
          className="flex h-10 w-full max-w-sm rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <select name="estagio" defaultValue={estagio ?? ""} aria-label="Estágio do funil" className={SELECT}>
          <option value="">Todos os estágios</option>
          {ESTAGIOS_FUNIL.map((e) => (
            <option key={e.valor} value={e.valor}>
              {e.rotulo}
            </option>
          ))}
        </select>
        <select
          name="temperatura"
          defaultValue={temperatura ?? ""}
          aria-label="Temperatura"
          className={SELECT}
        >
          <option value="">Todas as temperaturas</option>
          {TEMPERATURAS.map((t) => (
            <option key={t.valor} value={t.valor}>
              {t.rotulo}
            </option>
          ))}
        </select>
        <Button type="submit">Filtrar</Button>
        {filtrando && (
          <Link href="/clientes" className="text-sm text-muted-foreground hover:text-foreground">
            Limpar
          </Link>
        )}
      </form>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar os clientes</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {!error && clientes.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Nenhum cliente encontrado</p>
          <p className="mt-1 text-sm">
            {filtrando
              ? "Ajuste os filtros para ver mais clientes."
              : "Quem manda mensagem entra aqui sozinho. Você também pode cadastrar ou importar uma planilha."}
          </p>
        </div>
      )}

      {!error && clientes.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {clientes.map((c) => (
            <Link key={c.id} href={`/clientes/${c.id}`} className="block">
              <Card className="h-full transition-colors hover:border-foreground/20">
                <CardHeader>
                  <CardTitle className="truncate">
                    {c.nome ?? c.telefone}
                  </CardTitle>
                  <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                    {c.telefone}
                  </p>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {(c.lifecycle_stage || c.temperatura || c.score !== null) && (
                    <div className="flex flex-wrap items-center gap-2">
                      <ChipsLead cliente={c} curto />
                      {c.score !== null && (
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {c.score} pts
                        </span>
                      )}
                    </div>
                  )}
                  {c.email && (
                    <div className="text-muted-foreground">{c.email}</div>
                  )}
                  {c.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {c.tags.slice(0, 6).map((t) => (
                        <Badge key={t} variant="secondary">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
