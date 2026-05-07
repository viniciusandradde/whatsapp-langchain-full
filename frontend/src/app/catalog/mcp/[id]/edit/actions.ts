"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import {
  deleteMcpServer,
  testMcpServer,
  updateMcpServer,
  type McpServerUpdateInput,
  type McpTestResult,
} from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function updateMcpAction(
  id: number,
  formData: FormData
): Promise<void> {
  const body: McpServerUpdateInput = {
    nome: String(formData.get("nome") || "").trim() || undefined,
    descricao: String(formData.get("descricao") || "").trim() || null,
    tipo_conexao: (String(formData.get("tipo_conexao") || "").trim() || undefined) as McpServerUpdateInput["tipo_conexao"],
    url: String(formData.get("url") || "").trim() || null,
    comando: String(formData.get("comando") || "").trim() || null,
    args: String(formData.get("args") || "").trim() || null,
    ativo: formData.get("ativo") === "on",
  };
  try {
    await updateMcpServer(id, body);
  } catch (e) {
    redirect(
      `/catalog/mcp/${id}/edit?error=` + encodeURIComponent(toError(e))
    );
  }
  revalidatePath("/catalog/mcp");
  revalidatePath(`/catalog/mcp/${id}/edit`);
  redirect("/catalog/mcp");
}

export async function deleteMcpAction(id: number): Promise<void> {
  try {
    await deleteMcpServer(id);
  } catch (e) {
    redirect(
      `/catalog/mcp/${id}/edit?error=` + encodeURIComponent(toError(e))
    );
  }
  revalidatePath("/catalog/mcp");
  redirect("/catalog/mcp");
}

export async function testMcpAction(id: number): Promise<McpTestResult> {
  return testMcpServer(id);
}
