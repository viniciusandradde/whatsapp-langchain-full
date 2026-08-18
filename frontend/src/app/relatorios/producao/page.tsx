/**
 * /relatorios/producao — Relatório de produção (mig 173).
 *
 * Ferramenta de plataforma: fala do servidor inteiro (disco, containers, fila,
 * migrations), não de um cliente. Só superadmin — o mesmo guarda que a API
 * aplica em toda rota de `/api/relatorios/producao`, e o mesmo gesto do
 * relatório de uso por cliente.
 *
 * Quem PRODUZ o relatório é o script no host: ele tem acesso a docker, disco e
 * aos logs da Evolution, que o container não tem. Esta tela lê o que ele
 * publicou e enfileira pedidos.
 */

import { Activity, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { isMyAdmin } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { loadPainelAction } from "./actions";
import { ProducaoClient } from "./producao-client";

export const dynamic = "force-dynamic";

export default async function RelatorioProducaoPage() {
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
          O relatório de produção é exclusivo de superadministradores — ele
          mostra o estado do servidor que atende todos os clientes.
        </p>
      </div>
    );
  }

  const r = await loadPainelAction();

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Activity}
        titulo="Relatório de produção"
        descricao="Checagens automáticas do servidor, com redação por IA. Roda todo dia no horário configurado, e sob demanda."
      />
      {r.ok ? (
        <ProducaoClient inicial={r.data} />
      ) : (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
          {r.error}
        </div>
      )}
    </div>
  );
}
