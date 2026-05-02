import Link from "next/link";
import { UsersRound } from "lucide-react";

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
  searchParams: Promise<{ q?: string }>;
}

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

  let clientes: Awaited<ReturnType<typeof getClientes>>["clientes"] = [];
  let error: string | null = null;

  try {
    const data = await getClientes({ search, limit: 50 });
    clientes = data.clientes;
  } catch (e) {
    error =
      e instanceof Error ? e.message : "Erro desconhecido ao buscar clientes.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <UsersRound className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Clientes</h1>
      </div>

      <form className="flex max-w-md gap-2" action="/clientes" method="get">
        <input
          name="q"
          defaultValue={search ?? ""}
          placeholder="Buscar por nome ou telefone…"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <button
          type="submit"
          className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Buscar
        </button>
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
            {search
              ? "Ajuste o filtro ou aguarde uma nova mensagem inbound."
              : "Quando um inbound chegar, o cliente entra aqui automaticamente."}
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
