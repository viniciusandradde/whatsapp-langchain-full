"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createMenu, type MenuChatbotCreateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createMenuAction(formData: FormData): Promise<void> {
  const nome = String(formData.get("nome") || "").trim();
  const mensagem_boas_vindas = String(
    formData.get("mensagem_boas_vindas") || ""
  ).trim();
  const conexaoIdRaw = String(formData.get("conexao_id") || "").trim();
  const conexao_id =
    conexaoIdRaw && conexaoIdRaw !== "all" ? Number(conexaoIdRaw) : null;
  const triggersRaw = String(formData.get("trigger_keywords") || "").trim();
  const trigger_keywords = triggersRaw
    ? triggersRaw
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean)
    : undefined;

  if (!nome || !mensagem_boas_vindas) {
    redirect(
      "/menus/new?error=" +
        encodeURIComponent("Nome e mensagem de boas-vindas são obrigatórios.")
    );
  }

  let createdId: number;
  try {
    const body: MenuChatbotCreateInput = {
      nome,
      mensagem_boas_vindas,
      conexao_id,
      trigger_keywords,
    };
    const created = await createMenu(body);
    createdId = created.id;
  } catch (e) {
    redirect("/menus/new?error=" + encodeURIComponent(toError(e)));
  }
  revalidatePath("/menus");
  redirect(`/menus/${createdId}/edit`);
}
