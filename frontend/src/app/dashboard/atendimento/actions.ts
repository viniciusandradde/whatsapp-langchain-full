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
