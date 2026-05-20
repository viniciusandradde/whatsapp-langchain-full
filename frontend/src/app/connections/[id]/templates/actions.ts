"use server";

import { revalidatePath } from "next/cache";

import {
  createTemplate,
  deleteTemplate,
  importTemplatesFromMeta,
  syncTemplate,
  testSendTemplate,
  type WabaTemplate,
  type WabaTemplateInput,
} from "@/lib/api";

function safeError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createTemplateAction(
  conexaoId: number,
  body: WabaTemplateInput
) {
  try {
    const data = await createTemplate(conexaoId, body);
    revalidatePath(`/connections/${conexaoId}/templates`);
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function syncTemplateAction(conexaoId: number, templateId: number) {
  try {
    const data = await syncTemplate(conexaoId, templateId);
    revalidatePath(`/connections/${conexaoId}/templates`);
    return { ok: true as const, data: data as WabaTemplate };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function deleteTemplateAction(
  conexaoId: number,
  templateId: number
) {
  try {
    await deleteTemplate(conexaoId, templateId);
    revalidatePath(`/connections/${conexaoId}/templates`);
    return { ok: true as const };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function testSendTemplateAction(
  conexaoId: number,
  templateId: number,
  body: { to_number: string; variables: Record<string, string> }
) {
  try {
    const data = await testSendTemplate(conexaoId, templateId, body);
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}

export async function importFromMetaAction(conexaoId: number) {
  try {
    const data = await importTemplatesFromMeta(conexaoId);
    revalidatePath(`/connections/${conexaoId}/templates`);
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, error: safeError(e) };
  }
}
