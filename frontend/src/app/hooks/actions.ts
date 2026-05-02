"use server";

import { revalidatePath } from "next/cache";

import {
  createHook,
  deleteHook,
  getHookLogs,
  updateHook,
  type HookEvento,
  type HookInput,
  type HookLog,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type LogsResult =
  | { ok: true; logs: HookLog[] }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

function parseInput(form: FormData): HookInput {
  return {
    nome: String(form.get("nome") || "").trim(),
    evento: String(form.get("evento") || "") as HookEvento,
    url: String(form.get("url") || "").trim(),
    secret: ((form.get("secret") as string) || "").trim() || null,
    ativo: form.get("ativo") === "on",
  };
}

export async function saveHook(
  hookId: number | null,
  formData: FormData
): Promise<Result> {
  try {
    const input = parseInput(formData);
    if (!input.nome) return { ok: false, error: "Nome é obrigatório." };
    if (!input.evento) return { ok: false, error: "Evento é obrigatório." };
    if (!input.url) return { ok: false, error: "URL é obrigatória." };
    if (hookId) {
      await updateHook(hookId, input);
    } else {
      await createHook(input);
    }
    revalidatePath("/hooks");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteHookAction(hookId: number): Promise<Result> {
  try {
    await deleteHook(hookId);
    revalidatePath("/hooks");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadHookLogsAction(
  hookId: number
): Promise<LogsResult> {
  try {
    const data = await getHookLogs(hookId, 20);
    return { ok: true, logs: data.logs };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
