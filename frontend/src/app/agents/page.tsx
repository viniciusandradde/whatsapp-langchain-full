import Link from "next/link";
import { Bot, MessageSquare } from "lucide-react";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getAgents } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página de listagem de agentes configurados.
 *
 * Server Component que busca os agentes registrados via API
 * e exibe cada um como um card com link para suas conversas.
 */
export default async function AgentsPage() {
  await requireSession();

  // Tenta buscar agentes — a API pode não estar rodando em dev
  let agents: string[] = [];
  let error: string | null = null;

  try {
    const data = await getAgents();
    agents = data.agents;
  } catch (e) {
    error =
      e instanceof Error
        ? e.message
        : "Erro desconhecido ao buscar agentes";
  }

  return (
    <div className="space-y-6">
      {/* Cabeçalho da página */}
      <div className="flex items-center gap-2">
        <Bot className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">Agentes</h1>
      </div>

      {/* Estado de erro — API indisponível */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-medium">Não foi possível carregar os agentes</p>
          <p className="mt-1 text-destructive/80">{error}</p>
        </div>
      )}

      {/* Estado vazio — nenhum agente configurado */}
      {!error && agents.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          <Bot className="mx-auto h-10 w-10 mb-3 opacity-50" />
          <p className="font-medium">Nenhum agente configurado</p>
          <p className="mt-1 text-sm">
            Registre agentes no langgraph.json para vê-los aqui.
          </p>
        </div>
      )}

      {/* Grid de agentes — 1 coluna no mobile, 2 no tablet, 3 no desktop */}
      {agents.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agentId) => (
            <Card key={agentId}>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                    <Bot className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <CardTitle className="truncate">{agentId}</CardTitle>
                    <Badge variant="secondary" className="mt-1">
                      LangGraph
                    </Badge>
                  </div>
                </div>
              </CardHeader>

              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Agente registrado no langgraph.json
                </p>
              </CardContent>

              {/* Link para ver conversas filtradas por este agente */}
              <CardFooter>
                <Link
                  href={`/chats?agent=${encodeURIComponent(agentId)}`}
                  className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                >
                  <MessageSquare className="h-4 w-4" />
                  Ver conversas
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
