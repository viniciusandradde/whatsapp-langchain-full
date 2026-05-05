"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createAgenteIA, type AgenteIACreateInput } from "@/lib/api";

type Result =
  | { ok: false; error: string }
  | never; // success → redirect (não retorna)

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function createAgenteAction(
  formData: FormData
): Promise<Result> {
  const slug = String(formData.get("slug") || "").trim();
  const nome = String(formData.get("nome") || "").trim();
  const descricao = String(formData.get("descricao") || "").trim() || null;
  const template_catalog =
    String(formData.get("template_catalog") || "").trim() || "vsa_tech";

  if (!slug || !nome) {
    return { ok: false, error: "Slug e nome são obrigatórios." };
  }

  const body: AgenteIACreateInput = {
    slug,
    nome,
    descricao,
    template_catalog,
  };

  let createdSlug: string;
  try {
    const created = await createAgenteIA(body);
    createdSlug = created.slug;
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
  revalidatePath("/agents");
  redirect(`/agents/db/${createdSlug}`);
}
