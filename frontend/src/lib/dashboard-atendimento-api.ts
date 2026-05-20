/**
 * Tipos + helper do endpoint /api/dashboard/atendimento.
 *
 * Mantenho num arquivo separado pra evitar inflar o lib/api.ts gigante.
 */
import { apiFetch } from "./api";

export type Periodo = "hoje" | "7d" | "30d";

export interface KPIs {
  aguardando: number;
  em_andamento: number;
  resolvidos: number;
  abandonados: number;
  tempo_medio_espera_min: number;
  taxa_via_ia_pct: number;
}

export interface RowAguardando {
  id: number;
  protocolo: string | null;
  created_at: string | null;
  departamento_id: number | null;
  departamento_nome: string | null;
  cliente_nome: string;
  cliente_telefone: string | null;
  espera_min: number;
}

export interface RowSemResposta {
  id: number;
  protocolo: string | null;
  last_message_at: string | null;
  assigned_to_user_id: string | null;
  departamento_id: number | null;
  departamento_nome: string | null;
  cliente_nome: string;
  cliente_telefone: string | null;
  desde_ultima_min: number;
}

export interface ChartCriadosFinalizadosPoint {
  dia: string;
  criados: number;
  finalizados: number;
}

export interface ChartPorHoraPoint {
  hora: number;
  total: number;
}

export interface ChartPorDepartamentoPoint {
  departamento: string;
  total: number;
}

export interface Atendente {
  user_id: string;
  nome: string;
  email: string | null;
  status: string;
  status_at: string | null;
  is_active: boolean;
  atendimentos_abertos: number;
}

export interface AtendentesPayload {
  total: number;
  online_count: number;
  offline_count: number;
  items: Atendente[];
}

export interface DashboardPayload {
  periodo: Periodo;
  kpis: KPIs;
  tabelas: {
    aguardando: RowAguardando[];
    em_andamento_sem_resposta: RowSemResposta[];
  };
  charts: {
    criados_finalizados: ChartCriadosFinalizadosPoint[];
    por_hora: ChartPorHoraPoint[];
    por_departamento: ChartPorDepartamentoPoint[];
  };
  atendentes: AtendentesPayload;
  updated_at: string;
}

export async function getDashboardAtendimento(
  periodo: Periodo = "hoje"
): Promise<DashboardPayload> {
  return apiFetch<DashboardPayload>(
    `/api/dashboard/atendimento?periodo=${periodo}`
  );
}
