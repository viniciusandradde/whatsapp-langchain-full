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

// Sprint Q.5 — Server Action pra quota (apiFetch é server-only)
import type { QuotaSnapshot } from "@/lib/api";

export async function fetchQuotaAction(empresaId: number): Promise<
  { ok: true; quota: QuotaSnapshot } | { ok: false; error: string }
> {
  try {
    const quota = await apiFetch<QuotaSnapshot>(
      `/api/empresas/${empresaId}/quota`
    );
    return { ok: true, quota };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar quota",
    };
  }
}

export async function fetchCurrentEmpresaIdAction(): Promise<number | null> {
  try {
    const { cookies } = await import("next/headers");
    const c = (await cookies()).get("active_empresa_id")?.value;
    return c ? parseInt(c, 10) : 1; // fallback empresa 1
  } catch {
    return 1;
  }
}
