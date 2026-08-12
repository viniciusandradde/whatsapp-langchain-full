/**
 * /relatorios/uso — Módulo de Uso (mig 165).
 *
 * Ferramenta de plataforma: a VSA escolhe um cliente, confere o relatório do
 * mês e dispara o PDF no WhatsApp dele. Só superadmin — o mesmo guarda que a
 * API aplica em toda rota de `/api/relatorios/uso`.
 */

import { FileBarChart, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { isMyAdmin, type ClienteUso } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { loadClientesAction } from "./actions";
import { UsoClient } from "./uso-client";

export const dynamic = "force-dynamic";

export default async function RelatorioUsoPage() {
  await requireSession();

  let isAdmin = false;
  try {
    const r = await isMyAdmin();
    isAdmin = r.is_superadmin;
  } catch {
    isAdmin = false;
  }

  if (!isAdmin) {
    return (
      <div className="rounded-md border border-warning/40 bg-warning/10 p-6">
        <div className="flex items-center gap-3">
          <ShieldAlert className="size-5 text-warning" />
          <h1 className="text-lg font-semibold">Acesso restrito</h1>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          O módulo de uso é exclusivo de superadministradores — ele mostra dados
          de todos os clientes da plataforma e envia mensagem em nome deles.
        </p>
      </div>
    );
  }

  let clientes: ClienteUso[] = [];
  let erro: string | null = null;
  const r = await loadClientesAction();
  if (r.ok) clientes = r.data;
  else erro = r.error;

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Uso por cliente"
        descricao="Volume processado, arquivos lidos e tempo de resposta de cada cliente. Confira o mês, baixe o PDF e envie no WhatsApp dele."
        icon={FileBarChart}
      />

      {erro ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm">
          {erro}
        </div>
      ) : (
        <UsoClient clientes={clientes} />
      )}
    </div>
  );
}
