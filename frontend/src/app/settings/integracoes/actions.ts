"use server";

import { revalidatePath } from "next/cache";

import {
  disconnectGoogleCalendar,
  getGoogleCalendarOAuthUrl,
  updateGoogleCalendarConfig,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type UrlResult = { ok: true; url: string } | { ok: false; error: string };

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
