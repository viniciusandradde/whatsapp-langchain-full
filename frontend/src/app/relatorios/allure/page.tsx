/**
 * /relatorios/allure — Test Runner E2E (Sprint L).
 * Admin-only. Renderiza UI client component que dispara/monitora runs
 * + tabela histórica + iframe pro Allure HTML.
 */

import { ShieldAlert, FileBarChart } from "lucide-react";

import { getTestRuns, isMyAdmin, type TestRun } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { TestRunnerClient } from "./test-runner-client";

export const dynamic = "force-dynamic";

export default async function RelatoriosAlluraPage() {
  await requireSession();

  let isAdmin = false;
  try {
    const r = await isMyAdmin();
    isAdmin = r.is_superadmin;
  } catch {
    // Endpoint pode estar desabilitado (enable_test_runner=false) — trata
    // como não-admin pra UI mostrar mensagem amigável.
    isAdmin = false;
  }

  if (!isAdmin) {
    return (
      <div className="rounded-md border border-amber-300 bg-amber-50 p-6 dark:border-amber-700 dark:bg-amber-950/30">
        <div className="flex items-center gap-3">
          <ShieldAlert className="size-5 text-amber-700 dark:text-amber-300" />
          <h1 className="text-lg font-semibold">Acesso restrito</h1>
        </div>
        <p className="mt-2 text-sm text-amber-900 dark:text-amber-200">
          Esta página é exclusiva para superadministradores. Se você precisa
          de acesso, peça ao administrador da empresa para configurar a flag
          <code className="mx-1 font-mono">is_superadmin</code> no seu user.
        </p>
      </div>
    );
  }

  let runs: TestRun[] = [];
  let featureDisabled = false;
  let error: string | null = null;
  try {
    const r = await getTestRuns();
    runs = r.items;
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao listar runs.";
    if (/404/.test(msg)) {
      featureDisabled = true;
    } else {
      error = msg;
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <FileBarChart className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Relatórios E2E</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Bateria de testes end-to-end multi-setor com mídia (32 cenários).
            Allure HTML interativo após cada run.
          </p>
        </div>
      </div>

      {featureDisabled ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-6 dark:border-amber-700 dark:bg-amber-950/30">
          <div className="flex items-center gap-3">
            <ShieldAlert className="size-5 text-amber-700 dark:text-amber-300" />
            <h2 className="text-base font-semibold">
              Test runner desabilitado nesta instância
            </h2>
          </div>
          <p className="mt-2 text-sm text-amber-900 dark:text-amber-200">
            A imagem da API foi buildada sem as dependências de teste pra
            ficar leve em produção. Pra ativar:
          </p>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-amber-900 dark:text-amber-200">
            <li>
              No Dokploy, adicione no env do serviço{" "}
              <code className="font-mono">api</code>:{" "}
              <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900">
                ENABLE_TEST_RUNNER=true
              </code>
            </li>
            <li>
              Adicione build-arg{" "}
              <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900">
                ENABLE_TEST_RUNNER=true
              </code>{" "}
              no compose
            </li>
            <li>Faça rebuild + redeploy do compose</li>
            <li>
              Imagem cresce ~300MB (Java JRE + allure CLI + pytest + deepeval)
            </li>
          </ol>
        </div>
      ) : (
        <>
          {error && (
            <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          <TestRunnerClient initialRuns={runs} />
        </>
      )}
    </div>
  );
}
