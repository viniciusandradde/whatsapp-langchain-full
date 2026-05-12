import Link from "next/link";
import { Brain, Plus, Globe, Pencil, Lock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getModelosLLM } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * /catalog/models — catálogo de modelos LLM (mig 042 + 044 padrão profissional).
 *
 * Mostra:
 * - Modelos globais (empresa_id NULL) — read-only, seedados na mig 042
 * - Modelos custom da empresa (empresa_id preenchido) — editáveis
 *
 * Diferente de /models legacy que define qual modelo cada agente usa.
 * Aqui é o catálogo em si (provedor + nome + custo + janela).
 */
export default async function CatalogModelsPage() {
  await requireSession();

  let items: Awaited<ReturnType<typeof getModelosLLM>>["items"] = [];
  let error: string | null = null;
  try {
    const r = await getModelosLLM({ onlyActive: false });
    items = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao listar modelos.";
  }

  // Agrupar por (provedor, escopo)
  const globais = items.filter((m) => m.empresa_id === null);
  const custom = items.filter((m) => m.empresa_id !== null);

  const grupoFmt = (lista: typeof items) => {
    const porProvedor = new Map<string, typeof items>();
    for (const m of lista) {
      if (!porProvedor.has(m.provedor)) porProvedor.set(m.provedor, []);
      porProvedor.get(m.provedor)!.push(m);
    }
    return Array.from(porProvedor.entries()).sort(([a], [b]) =>
      a.localeCompare(b)
    );
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Brain className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Catálogo de modelos LLM</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Modelos disponíveis pra agentes IA — globais (read-only) +
              custom da empresa.
            </p>
          </div>
        </div>
        <Link href="/catalog/models/new">
          <Button>
            <Plus className="size-4" />
            Novo modelo custom
          </Button>
        </Link>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* Custom da empresa */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          <Pencil className="size-3.5" /> Custom desta empresa ({custom.length})
        </h2>
        {custom.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              Nenhum modelo custom. Globais já cobrem maioria dos casos —
              crie custom só pra modelos privados ou overrides de custo.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {custom.map((m) => (
              <ModeloCard key={m.id} m={m} />
            ))}
          </div>
        )}
      </section>

      {/* Globais */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          <Globe className="size-3.5" /> Globais ({globais.length})
        </h2>
        {grupoFmt(globais).map(([provedor, lista]) => (
          <div key={provedor}>
            <h3 className="mb-2 text-xs font-semibold text-muted-foreground/80">
              {provedor}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {lista.map((m) => (
                <ModeloCard key={m.id} m={m} readonly />
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

function ModeloCard({
  m,
  readonly,
}: {
  m: Awaited<ReturnType<typeof getModelosLLM>>["items"][0];
  readonly?: boolean;
}) {
  const tipoBadge: Record<typeof m.tipo, string> = {
    chat: "Chat",
    embedding: "Embedding",
    midia: "Mídia",
    audio: "Áudio",
    imagem: "Imagem",
  };
  return (
    <Card className="flex flex-col">
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{m.nome}</CardTitle>
          <div className="flex flex-wrap gap-1">
            {readonly && (
              <Badge variant="secondary" className="text-[10px]">
                <Lock className="mr-0.5 size-2.5" /> global
              </Badge>
            )}
            {!m.ativo && (
              <Badge variant="secondary" className="text-[10px]">
                inativo
              </Badge>
            )}
            <Badge variant="outline" className="text-[10px]">
              {tipoBadge[m.tipo]}
            </Badge>
          </div>
        </div>
        {m.descricao && (
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {m.descricao}
          </p>
        )}
      </CardHeader>
      <CardContent className="flex-1 space-y-1 text-xs text-muted-foreground">
        <p>
          <span className="font-mono text-foreground/80">
            {m.provedor}/{m.nome}
          </span>
        </p>
        {(m.custo_input_mtok !== null || m.custo_output_mtok !== null) && (
          <p>
            Custo: <code>${m.custo_input_mtok ?? "?"}/M in</code> ·{" "}
            <code>${m.custo_output_mtok ?? "?"}/M out</code>
          </p>
        )}
        {m.janela_contexto && (
          <p>Contexto: {m.janela_contexto.toLocaleString("pt-BR")} tokens</p>
        )}
        {!readonly && (
          <Link
            href={`/catalog/models/${m.id}/edit`}
            className="mt-2 inline-block text-xs text-primary hover:underline"
          >
            Editar →
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
