"use server";

import { apiFetch } from "@/lib/api";

interface OnboardingStatus {
  empresa_id: number | null;
  empresa_nome: string | null;
  empresa_doc_ok: boolean;
  conexoes_count: number;
  agentes_count: number;
  atendentes_count: number;
  completo: boolean;  // todos os 4 checks ok = onboarding completo
}

export async function fetchOnboardingStatusAction(): Promise<OnboardingStatus> {
  // Reusa endpoints existentes — não exige endpoint dedicado backend.
  try {
    const empresas = await apiFetch<{ empresas: Array<{ id: number; nome: string; doc: string | null }> }>(
      "/api/empresas"
    );
    const ativa = empresas.empresas[0]; // primeira é default na ordem do backend
    if (!ativa) {
      return {
        empresa_id: null,
        empresa_nome: null,
        empresa_doc_ok: false,
        conexoes_count: 0,
        agentes_count: 0,
        atendentes_count: 0,
        completo: false,
      };
    }

    const [conexoes, agentes, atendentes] = await Promise.all([
      apiFetch<{ conexoes: unknown[] }>("/api/conexoes").catch(() => ({ conexoes: [] })),
      apiFetch<{ items: unknown[] }>("/api/v1/agentes").catch(() => ({ items: [] })),
      apiFetch<{ items: unknown[] }>(`/api/empresas/${ativa.id}/membros`).catch(() => ({ items: [] })),
    ]);

    const conexoesCount = conexoes.conexoes?.length ?? 0;
    const agentesCount = agentes.items?.length ?? 0;
    const atendentesCount = atendentes.items?.length ?? 0;
    const docOk = !!ativa.doc;

    return {
      empresa_id: ativa.id,
      empresa_nome: ativa.nome,
      empresa_doc_ok: docOk,
      conexoes_count: conexoesCount,
      agentes_count: agentesCount,
      atendentes_count: atendentesCount,
      completo: docOk && conexoesCount > 0 && agentesCount > 0 && atendentesCount > 0,
    };
  } catch (e) {
    return {
      empresa_id: null,
      empresa_nome: null,
      empresa_doc_ok: false,
      conexoes_count: 0,
      agentes_count: 0,
      atendentes_count: 0,
      completo: false,
    };
  }
}
