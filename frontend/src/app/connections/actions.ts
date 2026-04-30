"use server";

import { revalidatePath } from "next/cache";

import {
  createConexao,
  disableConexao,
  updateConexao,
  type ConexaoInput,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

function parseInput(form: FormData): ConexaoInput {
  const provider = String(form.get("provider") || "twilio_sandbox") as ConexaoInput["provider"];
  const status = String(form.get("status") || "active") as ConexaoInput["status"];
  return {
    provider,
    sid: (form.get("sid") as string) || null,
    from_number: String(form.get("from_number") || "").trim(),
    display_name: (form.get("display_name") as string) || null,
    default_agent_id: String(form.get("default_agent_id") || "vsa_tech"),
    status,
    is_default: form.get("is_default") === "on",
  };
}

export async function saveConexao(
  conexaoId: number | null,
  formData: FormData
): Promise<Result> {
  try {
    const input = parseInput(formData);
    if (!input.from_number) {
      return { ok: false, error: "from_number é obrigatório." };
    }
    if (conexaoId) {
      await updateConexao(conexaoId, input);
    } else {
      await createConexao(input);
    }
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro desconhecido.",
    };
  }
}

export async function disableConexaoAction(
  conexaoId: number
): Promise<Result> {
  try {
    await disableConexao(conexaoId);
    revalidatePath("/connections");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro desconhecido.",
    };
  }
}
