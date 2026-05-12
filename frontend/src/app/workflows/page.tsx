import Link from "next/link";
import { Workflow as WorkflowIcon, Edit3 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { listWorkflows } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Página /workflows — workflows estilo state-machine (LangGraph state machines).
 *
 * Diferente de /menus (árvore simples), workflow é uma máquina de estado
 * declarativa com nodes tipados, vars persistidas, validação inline.
 * Use pra fluxos com coleta multi-step + LGPD + handover.
 */
export default async function WorkflowsPage() {
  await requireSession();

  let workflows: Awaited<ReturnType<typeof listWorkflows>> = [];
  let error: string | null = null;

  try {
    workflows = await listWorkflows();
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao listar workflows.";
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <WorkflowIcon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Workflows</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Máquinas de estado LangGraph para fluxos guiados (LGPD,
              triagem multi-step, handover com resumo).
            </p>
          </div>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {workflows.length === 0 && !error ? (
        <Card className="border-dashed">
          <CardContent className="space-y-3 py-10 text-center">
            <WorkflowIcon className="mx-auto size-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              Nenhum workflow cadastrado para esta empresa. Importe via{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                scripts/import_workflow_mackenzie.py
              </code>{" "}
              ou crie via SQL para começar.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workflows.map((w) => (
            <Card key={w.id} className="flex flex-col">
              <CardHeader className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base">{w.nome}</CardTitle>
                  <Badge
                    variant={w.ativo ? "default" : "secondary"}
                    className="shrink-0"
                  >
                    {w.ativo ? "Ativo" : "Inativo"}
                  </Badge>
                </div>
                <code className="text-xs text-muted-foreground">
                  {w.slug}
                </code>
              </CardHeader>
              <CardContent className="flex-1 space-y-1 text-xs text-muted-foreground">
                {w.descricao && <p>{w.descricao}</p>}
                <p>
                  Versão atual: <strong>{w.versao}</strong>
                  {w.versao_ativa_id && (
                    <>
                      {" "}· publicada #
                      <strong>{w.versao_ativa_id}</strong>
                    </>
                  )}
                </p>
                {w.updated_at && (
                  <p>
                    Atualizado:{" "}
                    {new Date(w.updated_at).toLocaleString("pt-BR")}
                  </p>
                )}
              </CardContent>
              <CardFooter>
                <Link href={`/workflows/${w.id}`} className="w-full">
                  <Button variant="outline" className="w-full">
                    <Edit3 className="size-4" />
                    Editar JSON
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
