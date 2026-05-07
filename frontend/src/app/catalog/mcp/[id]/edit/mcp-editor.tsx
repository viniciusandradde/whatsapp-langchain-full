"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import {
  ArrowLeft,
  Plug,
  Trash2,
  Zap,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { McpServer, McpTestResult } from "@/lib/api";

import { deleteMcpAction, testMcpAction, updateMcpAction } from "./actions";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";

export function McpEditor({
  mcp,
  initialError,
}: {
  mcp: McpServer;
  initialError: string | null;
}) {
  const [testResult, setTestResult] = useState<McpTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [_, startTransition] = useTransition();

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await testMcpAction(mcp.id);
      setTestResult(r);
    } catch (e) {
      setTestResult({
        ok: false,
        status: "error",
        erro: e instanceof Error ? e.message : String(e),
        tested_at: new Date().toISOString(),
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link
        href="/catalog/mcp"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Plug className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">{mcp.nome}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              MCP server · {mcp.tipo_conexao}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Badge variant={mcp.ativo ? "outline" : "secondary"}>
            {mcp.ativo ? "ativo" : "inativo"}
          </Badge>
          <Badge variant="outline">{mcp.status}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-base">Editar MCP server</CardTitle>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={runTest}
            disabled={testing}
          >
            {testing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Zap className="size-4" />
            )}
            Testar conexão
          </Button>
        </CardHeader>
        <CardContent>
          {initialError && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {initialError}
            </p>
          )}

          {testResult && (
            <div
              className={`mb-3 flex items-start gap-2 rounded-md border p-3 text-sm ${
                testResult.ok
                  ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "border-destructive/50 bg-destructive/10 text-destructive"
              }`}
            >
              {testResult.ok ? (
                <CheckCircle2 className="mt-0.5 size-4" />
              ) : (
                <AlertCircle className="mt-0.5 size-4" />
              )}
              <div>
                <p className="font-medium">
                  Status: {testResult.status}
                </p>
                {testResult.erro && (
                  <p className="text-xs mt-0.5">{testResult.erro}</p>
                )}
                <p className="text-xs opacity-70 mt-1">
                  Testado em {new Date(testResult.tested_at).toLocaleString("pt-BR")}
                </p>
              </div>
            </div>
          )}

          <form
            action={(fd: FormData) => {
              startTransition(async () => {
                await updateMcpAction(mcp.id, fd);
              });
            }}
            className="space-y-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className={labelCls}>Nome *</label>
                <input
                  name="nome"
                  defaultValue={mcp.nome}
                  required
                  maxLength={120}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Tipo de conexão</label>
                <select
                  name="tipo_conexao"
                  defaultValue={mcp.tipo_conexao}
                  className={inputCls}
                >
                  <option value="stdio">stdio (process spawn)</option>
                  <option value="http">http</option>
                  <option value="sse">sse</option>
                  <option value="websocket">websocket</option>
                </select>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Descrição</label>
                <input
                  name="descricao"
                  defaultValue={mcp.descricao ?? ""}
                  maxLength={500}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>URL</label>
                <input
                  name="url"
                  type="url"
                  defaultValue={mcp.url ?? ""}
                  maxLength={2000}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Comando (stdio)</label>
                <input
                  name="comando"
                  defaultValue={mcp.comando ?? ""}
                  maxLength={500}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Args</label>
                <input
                  name="args"
                  defaultValue={mcp.args ?? ""}
                  maxLength={2000}
                  className={inputCls}
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="ativo"
                defaultChecked={mcp.ativo}
                className="size-4"
              />
              MCP server ativo (disponível pra agentes)
            </label>

            <div className="flex justify-between gap-2 pt-2">
              <form
                action={async () => {
                  await deleteMcpAction(mcp.id);
                }}
              >
                <Button type="submit" variant="destructive">
                  <Trash2 className="size-4" />
                  Deletar
                </Button>
              </form>
              <Button type="submit">Salvar</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
