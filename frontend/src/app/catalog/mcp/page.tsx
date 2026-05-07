import Link from "next/link";
import { Plug, Plus, AlertCircle, CheckCircle2, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getMcpServers } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * /catalog/mcp — gestão MCP servers (mig 041 paridade ZigChat).
 *
 * MCP = Model Context Protocol. Permite ao agente IA chamar tools de
 * servidores externos (ex: filesystem, GitHub, Slack, custom). Cada
 * empresa cadastra os MCPs que quer disponíveis; agente vincula via
 * `mcp_server_ids` no editor.
 */
export default async function McpPage() {
  await requireSession();

  let items: Awaited<ReturnType<typeof getMcpServers>>["items"] = [];
  let error: string | null = null;
  try {
    const r = await getMcpServers({ onlyActive: false });
    items = r.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao listar MCP servers.";
  }

  const statusIcon = (s: string) => {
    if (s === "active") return <CheckCircle2 className="size-3 text-emerald-500" />;
    if (s === "error") return <AlertCircle className="size-3 text-destructive" />;
    return <Clock className="size-3 text-muted-foreground" />;
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Plug className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">MCP Servers</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Servidores Model Context Protocol — disponibilizam tools
              externas pros agentes IA.
            </p>
          </div>
        </div>
        <Link href="/catalog/mcp/new">
          <Button>
            <Plus className="size-4" />
            Novo MCP
          </Button>
        </Link>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {items.length === 0 && !error ? (
        <Card className="border-dashed">
          <CardContent className="py-10 text-center">
            <Plug className="mx-auto mb-3 size-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              Nenhum MCP server cadastrado. Adicione pra dar tools externas
              aos agentes (filesystem, GitHub, Slack, etc).
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((m) => (
            <Card key={m.id} className="flex flex-col">
              <CardHeader className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-sm">{m.nome}</CardTitle>
                  <div className="flex gap-1">
                    {!m.ativo && (
                      <Badge variant="secondary" className="text-[10px]">
                        inativo
                      </Badge>
                    )}
                    <Badge variant="outline" className="text-[10px]">
                      {m.tipo_conexao}
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
                {m.url && (
                  <p className="truncate" title={m.url}>
                    URL: <code>{m.url}</code>
                  </p>
                )}
                {m.comando && (
                  <p className="truncate" title={m.comando}>
                    Comando: <code>{m.comando}</code>
                  </p>
                )}
                <p className="flex items-center gap-1">
                  {statusIcon(m.status)} <span>{m.status}</span>
                  {m.ultimo_teste_at && (
                    <span className="text-muted-foreground/60">
                      · testado{" "}
                      {new Date(m.ultimo_teste_at).toLocaleString("pt-BR", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </span>
                  )}
                </p>
                {m.ultimo_erro && (
                  <p className="text-destructive/80">{m.ultimo_erro}</p>
                )}
                <Link
                  href={`/catalog/mcp/${m.id}/edit`}
                  className="mt-2 inline-block text-primary hover:underline"
                >
                  Editar →
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
