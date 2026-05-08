/**
 * /relatorios/allure/runs/{id} — Iframe full-viewport com Allure HTML.
 * Sprint L. Admin-only.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { headers } from "next/headers";

import { auth } from "@/lib/auth";
import { isMyAdmin } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

async function reportExists(runId: number): Promise<boolean> {
  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) return false;
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const token = process.env.INTERNAL_SERVICE_TOKEN || "";
    // GET (FastAPI não responde HEAD em rotas de GET por default).
    // Cancela após primeiros bytes — só importa o status code.
    const controller = new AbortController();
    const r = await fetch(
      `${apiUrl}/api/admin/tests/runs/${runId}/report`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "X-User-Id": session.user.id,
        },
        cache: "no-store",
        signal: controller.signal,
      }
    );
    controller.abort();
    return r.ok;
  } catch {
    return false;
  }
}

export default async function RunDetailPage({ params }: Props) {
  await requireSession();
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) notFound();

  let isAdmin = false;
  try {
    const r = await isMyAdmin();
    isAdmin = r.is_superadmin;
  } catch {
    isAdmin = false;
  }
  if (!isAdmin) notFound();

  const hasReport = await reportExists(runId);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Link
          href="/relatorios/allure"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar
        </Link>
        <span className="text-xs text-muted-foreground">
          Run #{runId} — Allure HTML
        </span>
      </div>
      {hasReport ? (
        <iframe
          src={`/api/proxy/admin-tests/runs/${runId}/report`}
          title={`Allure Report Run #${runId}`}
          className="h-[calc(100vh-9rem)] w-full rounded-md border"
        />
      ) : (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-6 dark:border-amber-700 dark:bg-amber-950/30">
          <div className="flex items-center gap-3">
            <AlertTriangle className="size-5 text-amber-700 dark:text-amber-300" />
            <h2 className="text-base font-semibold">
              Relatório Allure não disponível
            </h2>
          </div>
          <p className="mt-2 text-sm text-amber-900 dark:text-amber-200">
            Esse run não tem HTML do Allure. Possíveis causas:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900 dark:text-amber-200">
            <li>
              Tests crasharam antes de gerar artifacts (erro de setup/fixture)
            </li>
            <li>
              Allure CLI falhou ao gerar HTML (verificar logs do container
              tests)
            </li>
            <li>Run cancelado via "Parar"</li>
          </ul>
          <p className="mt-3 text-sm text-amber-900 dark:text-amber-200">
            Veja os logs do run na tela anterior pra entender o erro.
          </p>
        </div>
      )}
    </div>
  );
}
