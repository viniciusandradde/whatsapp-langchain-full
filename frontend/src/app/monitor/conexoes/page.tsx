import { Activity } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/components/ui/api-error";
import {
  getMonitorConexoes,
  isMyAdmin,
  type MonitorConexoesResposta,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

import { MonitorClient } from "./monitor-client";

export const dynamic = "force-dynamic";

/**
 * /monitor/conexoes — "Saúde dos clientes" (mig 196): todas as conexões de
 * WhatsApp de todos os clientes com estado, última mensagem recebida,
 * recebidas × esperadas nas últimas 24 h e os episódios abertos. Quem
 * escreve é o tick do worker; aqui só se lê o banco — o mesmo que alimenta
 * o aviso no canal da plataforma.
 *
 * Superadmin-only: o guard real é do backend; a page repete a checagem para
 * não renderizar uma tela de erros a quem não deve vê-la (padrão
 * /catalog/openrouter).
 */
export default async function MonitorConexoesPage() {
  await requireSession();

  let isAdmin = false;
  try {
    isAdmin = (await isMyAdmin()).is_superadmin;
  } catch {
    isAdmin = false;
  }
  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <PageHeader
          titulo="Saúde dos clientes"
          descricao="Conexões de WhatsApp de todos os clientes."
          icon={Activity}
        />
        <p className="text-sm text-muted-foreground">
          Acesso restrito à administração da plataforma.
        </p>
      </div>
    );
  }

  let inicial: MonitorConexoesResposta | null = null;
  let error: unknown = null;
  try {
    inicial = await getMonitorConexoes();
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Saúde dos clientes"
        descricao="Conexões de WhatsApp de todos os clientes: estado, última mensagem recebida e alertas. Verificadas a cada 5 minutos; o canal da plataforma recebe os avisos."
        icon={Activity}
      />
      {error || !inicial ? (
        <ApiError variant="card" error={error} />
      ) : (
        <MonitorClient inicial={inicial} />
      )}
    </div>
  );
}
