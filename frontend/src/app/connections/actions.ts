"use server";

import { revalidatePath } from "next/cache";

import {
  createConexao,
  disableConexao,
  disconnectConexao,
  evolutionProvision,
  getConexao,
  getConexaoQR,
  getConexaoQuota,
  getConexaoStatus,
  regeneratePairingCode,
  patchConexao,
  testConexao,
  getWabaConfig,
  testEvolutionConnection,
  wabaEmbeddedSignup,
  wabaFinalize,
  wabaOAuthResult,
  wabaOAuthStart,
  wabaSincronizar,
  wabaManual,
  type ConexaoInput,
  type ConexaoPatchInput,
  type ConexaoQuota,
  type EvolutionProvisionInput,
  type TestEvolutionResult,
  type WabaEmbeddedSignupInput,
  type WabaFinalizeInput,
  type WabaManualInput,
} from "@/lib/api";

type ActionResult<T = void> =
  | { ok: true; data?: T }
  | { ok: false; error: string };

function safeError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createConexaoAction(
  input: ConexaoInput
): Promise<ActionResult> {
  try {
    if (!input.from_number) {
      return { ok: false, error: "Número (from_number) é obrigatório." };
    }
    await createConexao(input);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function patchConexaoAction(
  id: number,
  body: ConexaoPatchInput
): Promise<ActionResult> {
  try {
    await patchConexao(id, body);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function getConexaoQuotaAction(
  id: number
): Promise<ActionResult<ConexaoQuota>> {
  try {
    const data = await getConexaoQuota(id);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function deleteConexaoAction(id: number): Promise<ActionResult> {
  try {
    await disableConexao(id);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function testEvolutionAction(input: {
  api_url: string;
  api_key: string;
  instance_name: string;
}): Promise<TestEvolutionResult> {
  try {
    return await testEvolutionConnection(input);
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

// --- WABA OAuth ---

export async function wabaOAuthStartAction(
  displayName?: string
): Promise<ActionResult<{ redirect_url: string; state: string }>> {
  try {
    const data = await wabaOAuthStart(displayName);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function wabaOAuthResultAction(state: string) {
  try {
    return { ok: true as const, data: await wabaOAuthResult(state) };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

// --- WABA Embedded Signup (FB JS SDK — método oficial Meta) ---

export async function getWabaConfigAction() {
  try {
    return { ok: true as const, data: await getWabaConfig() };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function wabaEmbeddedSignupAction(
  body: WabaEmbeddedSignupInput
): Promise<ActionResult> {
  try {
    await wabaEmbeddedSignup(body);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function wabaFinalizeAction(
  body: WabaFinalizeInput
): Promise<ActionResult> {
  try {
    await wabaFinalize(body);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

// --- Evolution auto-provision ---

export async function evolutionProvisionAction(input: EvolutionProvisionInput) {
  try {
    const data = await evolutionProvision(input);
    revalidatePath("/connections");
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function refreshQRAction(conexaoId: number) {
  try {
    return { ok: true as const, data: await getConexaoQR(conexaoId) };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function regeneratePairingCodeAction(
  conexaoId: number,
  phoneNumber: string
) {
  try {
    return {
      ok: true as const,
      data: await regeneratePairingCode(conexaoId, phoneNumber),
    };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function pollStatusAction(conexaoId: number) {
  try {
    return { ok: true as const, data: await getConexaoStatus(conexaoId) };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function testConexaoAction(conexaoId: number) {
  try {
    return { ok: true as const, data: await testConexao(conexaoId) };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function disconnectConexaoAction(conexaoId: number) {
  try {
    const data = await disconnectConexao(conexaoId);
    revalidatePath("/connections");
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function wabaManualAction(
  body: WabaManualInput
): Promise<ActionResult> {
  try {
    await wabaManual(body);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: safeError(e) };
  }
}

export async function wabaSincronizarAction(conexaoId: number) {
  try {
    const data = await wabaSincronizar(conexaoId);
    revalidatePath(`/connections/${conexaoId}`);
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function refreshConexaoAction(conexaoId: number) {
  try {
    return { ok: true as const, data: await getConexao(conexaoId) };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function loadAgentesEmpresaAction(): Promise<
  | { ok: true; data: { slug: string; nome: string }[] }
  | { ok: false; error: string }
> {
  try {
    const { getAgentesIA } = await import("@/lib/api");
    const { items } = await getAgentesIA({ onlyActive: true });
    return {
      ok: true,
      data: items.map((a) => ({ slug: a.slug, nome: a.nome })),
    };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar agentes.",
    };
  }
}
