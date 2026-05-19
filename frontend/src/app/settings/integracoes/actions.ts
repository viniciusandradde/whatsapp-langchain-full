"use server";

import { revalidatePath } from "next/cache";

import {
  deleteWarelineConfig,
  disconnectGoogleCalendar,
  getGoogleCalendarOAuthUrl,
  getWarelineConfig,
  saveWarelineConfig,
  testWarelineConnection,
  updateGoogleCalendarConfig,
  type WarelineConfig,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type UrlResult = { ok: true; url: string } | { ok: false; error: string };
type WarelineResult =
  | { ok: true; config: WarelineConfig | null }
  | { ok: false; error: string };
type WarelineTestResult =
  | { ok: boolean; mensagem: string }
  | { ok: false; mensagem: string; error: string };

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

// --- Wareline ConecteHub ---

export async function loadWarelineConfigAction(): Promise<WarelineResult> {
  try {
    const config = await getWarelineConfig();
    return { ok: true, config };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function saveWarelineConfigAction(payload: {
  username?: string;
  password?: string;
  client_id?: string;
  client_secret?: string;
  base_url?: string;
  pacientes_base_url?: string;
  ativo?: boolean;
}): Promise<WarelineResult> {
  try {
    const config = await saveWarelineConfig(payload);
    revalidatePath("/settings/integracoes");
    return { ok: true, config };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function testWarelineAction(): Promise<WarelineTestResult> {
  try {
    const r = await testWarelineConnection();
    return { ok: r.ok, mensagem: r.mensagem };
  } catch (e) {
    return { ok: false, mensagem: toError(e), error: toError(e) };
  }
}

export async function deleteWarelineConfigAction(): Promise<Result> {
  try {
    await deleteWarelineConfig();
    revalidatePath("/settings/integracoes");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
