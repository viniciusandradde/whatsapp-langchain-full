"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createAgenteIA, type AgenteIACreateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

/**
 * Server action passada pra <form action>. Next.js exige retorno void.
 * - Sucesso → redirect (throws — Next captura).
 * - Validação inválida → redirect pra ?error=... (mostrado pelo searchParams
 *   no page.tsx).
 * - Erro de API → throw (error boundary do segmento captura).
 */
export async function createAgenteAction(formData: FormData): Promise<void> {
  const slug = String(formData.get("slug") || "").trim();
  const nome = String(formData.get("nome") || "").trim();
  const descricao = String(formData.get("descricao") || "").trim() || null;
  const template_catalog =
    String(formData.get("template_catalog") || "").trim() || "vsa_tech";

  if (!slug || !nome) {
    redirect("/agents/new?error=" + encodeURIComponent("Slug e nome são obrigatórios."));
  }

  let createdSlug: string | undefined;
  try {
    const body: AgenteIACreateInput = { slug, nome, descricao, template_catalog };
    const created = await createAgenteIA(body);
    createdSlug = created.slug;
  } catch (e) {
    redirect("/agents/new?error=" + encodeURIComponent(toError(e)));
  }
  revalidatePath("/agents");
  redirect(`/agents/db/${createdSlug!}`);
}
