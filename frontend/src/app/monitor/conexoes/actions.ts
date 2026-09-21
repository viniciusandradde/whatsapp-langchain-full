"use server";

import type { BannerConexaoResposta, MonitorConexoesResposta } from "@/lib/api";

type Resultado<T> = { ok: true; data: T } | { ok: false; error: string };

function msg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

/** Superadmin — a tabela de "Saúde dos clientes" (revalida a cada minuto no cliente). */
export async function loadMonitorAction(): Promise<
  Resultado<MonitorConexoesResposta>
> {
  try {
    const { getMonitorConexoes } = await import("@/lib/api");
    return { ok: true, data: await getMonitorConexoes() };
  } catch (e) {
    return {
      ok: false,
      error: msg(e, "Não foi possível carregar a saúde das conexões."),
    };
  }
}

/** Empresa ativa — conexões caídas para o banner do painel. */
export async function loadBannerConexaoAction(): Promise<
  Resultado<BannerConexaoResposta>
> {
  try {
    const { getMonitorBanner } = await import("@/lib/api");
    return { ok: true, data: await getMonitorBanner() };
  } catch (e) {
    return {
      ok: false,
      error: msg(e, "Não foi possível verificar as conexões."),
    };
  }
}
