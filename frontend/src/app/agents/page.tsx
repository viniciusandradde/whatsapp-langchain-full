import Link from "next/link";
import { Bot, MessageSquare, Plus, SlidersHorizontal, Star } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAgentesIA, getAgents } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { DeactivateAllAgentesButton } from "./deactivate-all-button";

export const dynamic = "force-dynamic";

/**
 * Página /agents — lista híbrida pós Sub-fase A.
 *
 * - **Agentes DB** (agente_ia table): cadastráveis via UI em /agents/new,
 *   editáveis em /agents/db/[slug] com 5 tabs.
 * - **Templates do catálogo Python**: código fonte em agents/catalog/<id>,
 *   editáveis em /agents/[id]/edit (override de prompt do legacy).
 *
 * Ambos co-existem; agente DB usa template_catalog pra reusar graph Python.
 */
export default async function AgentsPage() {
  await requireSession();

  let agentesDb: Awaited<ReturnType<typeof getAgentesIA>>["items"] = [];
  let agentesCatalog: string[] = [];
  let dbError: string | null = null;
  let catalogError: string | null = null;

  try {
    const r = await getAgentesIA();
    agentesDb = r.items;
  } catch (e) {
    dbError = e instanceof Error ? e.message : "Erro ao listar agentes DB.";
  }
  try {
    const r = await getAgents();
    agentesCatalog = r.agents;
  } catch (e) {
    catalogError = e instanceof Error ? e.message : "Erro catálogo.";
  }

  return (
    <div className="space-y-8">
      <PageHeader
        titulo="Agentes"
        descricao="Quem responde pelo WhatsApp no seu lugar. Cada agente tem instruções, base de conhecimento e modelo próprios."
        icon={Bot}
        acoes={
          <>
            <DeactivateAllAgentesButton
              ativosCount={agentesDb.filter((a) => a.ativo).length}
            />
            <ButtonLink href="/agents/new">
              <Plus className="size-4" />
              Novo agente
            </ButtonLink>
          </>
        }
      />

      {/* ---- Agentes DB (cadastrados via UI) ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Cadastrados ({agentesDb.length})
        </h2>
        {dbError && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {dbError}
          </p>
        )}
        {!dbError && agentesDb.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center">
              <Bot className="mx-auto mb-2 size-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                Nenhum agente cadastrado ainda. Use{" "}
                <Link href="/agents/new" className="text-brand-primary underline">
                  Novo agente
                </Link>{" "}
                pra criar o primeiro.
              </p>
            </CardContent>
          </Card>
        )}
        {agentesDb.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {agentesDb.map((a) => (
              <Card key={a.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      {a.nome}
                      {a.is_default && (
                        <Star className="size-3.5 fill-brand-primary text-brand-primary" />
                      )}
                    </CardTitle>
                    {!a.ativo && <Badge variant="outline">inativo</Badge>}
                  </div>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {a.slug}
                  </p>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  {a.descricao && <p>{a.descricao}</p>}
                  <p>
                    Modelo: <code>{a.modelo ?? "—"}</code>
                  </p>
                  <p>
                    Estilo:{" "}
                    <Badge variant="outline" className="text-[10px]">
                      {a.estilo_resposta}
                    </Badge>{" "}
                    · temp {a.temperatura_efetiva.toFixed(2)} · top_p{" "}
                    {a.top_p_efetivo.toFixed(2)}
                  </p>
                  <p>
                    {a.tools_enabled.length} tools ·{" "}
                    {a.base_conhecimento_ids.length} KBs
                  </p>
                </CardContent>
                <CardFooter className="gap-2">
                  {/* `outline`, não `default`: com 9 agentes a tela tinha 9
                      botões na cor primária, e a ação primária de verdade
                      ("Novo agente") sumia no meio. Uma por tela (ADR-014). */}
                  <ButtonLink
                    href={`/agents/db/${a.slug}`}
                    variant="outline"
                    size="sm"
                    className="w-full flex-1"
                  >
                    <SlidersHorizontal className="size-3.5" />
                    Editar
                  </ButtonLink>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* ---- Agentes catálogo (código Python) ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Templates do catálogo ({agentesCatalog.length})
        </h2>
        {catalogError && (
          <p className="text-xs text-muted-foreground">{catalogError}</p>
        )}
        {agentesCatalog.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {agentesCatalog.map((id) => (
              <Card key={id}>
                <CardHeader>
                  <CardTitle className="text-base">{id}</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Código em <code>agents/catalog/{id}/</code>
                  </p>
                </CardHeader>
                <CardFooter className="gap-2">
                  <Link href={`/agents/${id}/edit`} className="flex-1">
                    <Button variant="ghost" size="sm" className="w-full">
                      <SlidersHorizontal className="size-3.5" />
                      Override prompt
                    </Button>
                  </Link>
                  <Link href={`/chats?agent=${id}`}>
                    <Button variant="ghost" size="sm">
                      <MessageSquare className="size-3.5" />
                    </Button>
                  </Link>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
