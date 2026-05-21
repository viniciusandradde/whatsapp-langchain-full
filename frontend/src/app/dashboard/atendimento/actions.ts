"use server";

import { apiFetch } from "@/lib/api";
import type {
  DashboardPayload,
  Periodo,
} from "@/lib/dashboard-atendimento-api";

/**
 * Server Action: busca payload do dashboard.
 * Chamada do client via dashboard-client.tsx (auto-refresh).
 */
export async function fetchDashboardAtendimentoAction(
  periodo: Periodo = "hoje"
): Promise<DashboardPayload> {
  return apiFetch<DashboardPayload>(
    `/api/dashboard/atendimento?periodo=${periodo}`
  );
}

interface ZumbisPreview {
  enabled: boolean;
  aguardando_zumbi: number;
  em_andamento_zumbi: number;
  total: number;
  config: {
    enabled: boolean;
    dias_max_aguardando: number;
    dias_max_sem_resposta: number;
  };
}

interface ZumbisCleanupResult {
  enabled: boolean;
  aguardando_fechados: number;
  em_andamento_fechados: number;
  total: number;
  dry_run: boolean;
  ids?: number[];
}

export async function previewZumbisAction(): Promise<ZumbisPreview> {
  return apiFetch<ZumbisPreview>(
    "/api/atendimentos/cleanup-zumbis/preview"
  );
}

export async function cleanupZumbisAction(
  dryRun = false
): Promise<ZumbisCleanupResult> {
  return apiFetch<ZumbisCleanupResult>(
    `/api/atendimentos/cleanup-zumbis?dry_run=${dryRun}`,
    { method: "POST" }
  );
}
