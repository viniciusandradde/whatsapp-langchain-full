/**
 * /relatorios/allure/runs/{id} — Iframe full-viewport com Allure HTML.
 * Sprint L. Admin-only.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { isMyAdmin } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
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
      <iframe
        src={`/api/proxy/admin-tests/runs/${runId}/report`}
        title={`Allure Report Run #${runId}`}
        className="h-[calc(100vh-9rem)] w-full rounded-md border"
      />
    </div>
  );
}
