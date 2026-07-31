"use server";

import { revalidatePath } from "next/cache";

import {
  type ApiConnection,
  createApiConnection,
  deleteApiConnection,
  disconnectGoogleCalendar,
  getApiConnectionProviders,
  getGoogleCalendarOAuthUrl,
  listApiConnections,
  type ProviderSpec,
  saveAsaasConfig,
  testApiConnection,
  testAsaasConnection,
  updateApiConnection,
  updateGoogleCalendarConfig,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type UrlResult = { ok: true; url: string } | { ok: false; error: string };
type ConnectionsResult =
  | { ok: true; connections: ApiConnection[] }
  | { ok: false; error: string };
type ConnectionResult =
  | { ok: true; connection: ApiConnection }
  | { ok: false; error: string };
type ProvidersResult =
  | { ok: true; providers: ProviderSpec[] }
  | { ok: false; error: string };
type TestResult = { ok: boolean; mensagem: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function startGoogleCalendarOAuthAction(): Promise<UrlResult> {
  try {
    const data = await getGoogleCalendarOAuthUrl();
    return { ok: true, url: data.authorize_url };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function disconnectGoogleCalendarAction(): Promise<Result> {
  try {
    await disconnectGoogleCalendar();
    revalidatePath("/settings/integracoes");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateAprovadorTelefoneAction(
  telefone: string
): Promise<Result> {
  try {
    await updateGoogleCalendarConfig({ aprovador_telefone: telefone });
    revalidatePath("/settings/integracoes");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Conector API genérico ---

export async function loadApiProvidersAction(
  includeLegacy = false
): Promise<ProvidersResult> {
  try {
    const r = await getApiConnectionProviders(includeLegacy);
    return { ok: true, providers: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadApiConnectionsAction(): Promise<ConnectionsResult> {
  try {
    const r = await listApiConnections();
    return { ok: true, connections: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createApiConnectionAction(payload: {
  provider_slug: string;
  label: string;
  credentials: Record<string, unknown>;
  base_url?: string;
  extra_config?: Record<string, unknown>;
  ativo?: boolean;
}): Promise<ConnectionResult> {
  try {
    const conn = await createApiConnection(payload);
    revalidatePath("/settings/integracoes");
    return { ok: true, connection: conn };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateApiConnectionAction(
  id: number,
  payload: {
    label?: string;
    base_url?: string;
    credentials_patch?: Record<string, unknown>;
    extra_config?: Record<string, unknown>;
    ativo?: boolean;
  }
): Promise<ConnectionResult> {
  try {
    const conn = await updateApiConnection(id, payload);
    revalidatePath("/settings/integracoes");
    return { ok: true, connection: conn };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function testApiConnectionAction(
  id: number
): Promise<TestResult> {
  try {
    return await testApiConnection(id);
  } catch (e) {
    return { ok: false, mensagem: toError(e) };
  }
}

export async function deleteApiConnectionAction(
  id: number
): Promise<Result> {
  try {
    await deleteApiConnection(id);
    revalidatePath("/settings/integracoes");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Asaas (config global da plataforma — superadmin) ---

export async function saveAsaasConfigAction(payload: {
  environment?: string;
  api_key?: string;
  webhook_token?: string;
  success_url?: string;
  cancel_url?: string;
}): Promise<Result> {
  try {
    await saveAsaasConfig(payload);
    revalidatePath("/settings/integracoes");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function testAsaasAction(): Promise<TestResult> {
  try {
    const r = await testAsaasConnection();
    if (r.ok) return { ok: true, mensagem: `Conta Asaas: ${r.conta}` };
    return {
      ok: false,
      mensagem: r.erro || "Falha ao validar a credencial Asaas.",
    };
  } catch (e) {
    return { ok: false, mensagem: toError(e) };
  }
}
