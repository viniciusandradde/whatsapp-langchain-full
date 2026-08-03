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
  dispensado: boolean;  // clicou em "Pular" alguma vez (mig 160)
}

const VAZIO: OnboardingStatus = {
  empresa_id: null,
  empresa_nome: null,
  empresa_doc_ok: false,
  conexoes_count: 0,
  agentes_count: 0,
  atendentes_count: 0,
  completo: false,
  dispensado: false,
};

/**
 * Estado do onboarding da empresa ativa.
 *
 * Vem de um endpoint único (`GET /api/empresas/{id}/onboarding`) e não mais de
 * 4 listagens contadas aqui. Aquele desenho tinha duas armadilhas silenciosas,
 * ambas terminando no mesmo lugar — o wizard reaparecendo em todo login:
 * `/membros` devolve lista pura e o código lia `.items` dela (dava 0 com 10
 * atendentes), e `/v1/agentes` exige a permissão `agente.config`, então
 * operador comum tomava 403 e o passo 3 nunca completava.
 */
export async function fetchOnboardingStatusAction(): Promise<OnboardingStatus> {
  try {
    const empresas = await apiFetch<{ empresas: Array<{ id: number }> }>(
      "/api/empresas"
    );
    const ativa = empresas.empresas[0]; // primeira é default (ORDER BY is_default DESC)
    if (!ativa) return VAZIO;
    return await apiFetch<OnboardingStatus>(
      `/api/empresas/${ativa.id}/onboarding`
    );
  } catch {
    // Falha de rede/API não pode prender ninguém no wizard: sem saber o
    // estado real, o menos pior é deixar passar pro painel.
    return { ...VAZIO, dispensado: true };
  }
}

/**
 * Grava o "Pular pra agora" (mig 160), pra o wizard não voltar no próximo login.
 *
 * Devolve `false` se não deu — o botão navega assim mesmo, porque prender o
 * usuário na tela por causa de uma escrita que falhou seria pior do que ele
 * ver o wizard de novo amanhã.
 */
export async function dispensarOnboardingAction(
  empresaId: number,
  dispensado = true
): Promise<boolean> {
  try {
    await apiFetch(`/api/empresas/${empresaId}/onboarding-dispensado`, {
      method: "PUT",
      body: { dispensado },
    });
    return true;
  } catch {
    return false;
  }
}
