"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createMcpServer, type McpServerCreateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createMcpAction(formData: FormData): Promise<void> {
  const nome = String(formData.get("nome") || "").trim();
  const tipo_conexao = String(formData.get("tipo_conexao") || "stdio").trim() as McpServerCreateInput["tipo_conexao"];
  const descricao = String(formData.get("descricao") || "").trim() || null;
  const url = String(formData.get("url") || "").trim() || null;
  const comando = String(formData.get("comando") || "").trim() || null;
  const args = String(formData.get("args") || "").trim() || null;

  if (!nome) {
    redirect(
      "/catalog/mcp/new?error=" + encodeURIComponent("Nome é obrigatório.")
    );
  }
  if (tipo_conexao === "stdio" && !comando) {
    redirect(
      "/catalog/mcp/new?error=" +
        encodeURIComponent("MCP stdio precisa de `comando`.")
    );
  }
  if (tipo_conexao !== "stdio" && !url) {
    redirect(
      "/catalog/mcp/new?error=" +
        encodeURIComponent(`MCP ${tipo_conexao} precisa de URL.`)
    );
  }

  let createdId: number | undefined;
  try {
    const created = await createMcpServer({
      nome,
      tipo_conexao,
      descricao,
      url,
      comando,
      args,
    });
    createdId = created.id;
  } catch (e) {
    redirect("/catalog/mcp/new?error=" + encodeURIComponent(toError(e)));
  }
  revalidatePath("/catalog/mcp");
  redirect(`/catalog/mcp/${createdId!}/edit`);
}
