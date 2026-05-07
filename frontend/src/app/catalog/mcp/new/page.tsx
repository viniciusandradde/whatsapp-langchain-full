import Link from "next/link";
import { ArrowLeft, Plug } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireSession } from "@/lib/session";

import { createMcpAction } from "./actions";

export const dynamic = "force-dynamic";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

interface PageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function NewMcpPage({ searchParams }: PageProps) {
  await requireSession();
  const errorMsg = (await searchParams).error ?? null;

  return (
    <div className="space-y-6">
      <Link
        href="/catalog/mcp"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Plug className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Novo MCP server</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Servidor Model Context Protocol (stdio/sse/http/websocket).
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configuração</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMsg && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMsg}
            </p>
          )}
          <form action={createMcpAction} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className={labelCls}>Nome *</label>
                <input
                  name="nome"
                  required
                  maxLength={120}
                  placeholder="Ex: filesystem-mcp"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Tipo de conexão *</label>
                <select
                  name="tipo_conexao"
                  defaultValue="stdio"
                  className={inputCls}
                >
                  <option value="stdio">stdio (process spawn)</option>
                  <option value="http">http</option>
                  <option value="sse">sse (server-sent events)</option>
                  <option value="websocket">websocket</option>
                </select>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Descrição</label>
                <input
                  name="descricao"
                  maxLength={500}
                  placeholder="Ex: Filesystem MCP — leitura de arquivos do projeto"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>URL (http/sse/websocket)</label>
                <input
                  name="url"
                  type="url"
                  maxLength={2000}
                  placeholder="https://mcp.example.com/sse"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Comando (stdio)</label>
                <input
                  name="comando"
                  maxLength={500}
                  placeholder="npx @modelcontextprotocol/server-filesystem"
                  className={inputCls}
                />
                <p className={helpCls}>
                  ⚠️ Test de stdio não roda no servidor por segurança — valide
                  manualmente no shell antes.
                </p>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Args (JSON ou string)</label>
                <input
                  name="args"
                  maxLength={2000}
                  placeholder='Ex: ["/path/to/dir"] ou texto livre'
                  className={inputCls}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Link href="/catalog/mcp">
                <Button type="button" variant="outline">
                  Cancelar
                </Button>
              </Link>
              <Button type="submit">Criar e editar</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
