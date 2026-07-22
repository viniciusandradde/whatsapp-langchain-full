"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createAgenteIA, type AgenteIACreateInput } from "@/lib/api";

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

/**
 * Normaliza o que o usuário digitou pro formato que o backend exige
 * (^[a-z][a-z0-9_-]{1,60}$). "Agente-Pessoal" → "agente-pessoal".
 * O `pattern` do input ajuda ao vivo, mas não dá pra confiar só nele
 * (página stale pós-deploy submete sem a validação atual).
 */
function slugify(raw: string): string {
  return raw
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // acentos (combining marks pós-NFD)
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-") // espaços e inválidos → hífen
    .replace(/-{2,}/g, "-")
    .replace(/^[^a-z]+/, "") // precisa começar com letra
    .replace(/-+$/, "")
    .slice(0, 60);
}

/**
 * Server action passada pra <form action>. Next.js exige retorno void.
 * - Sucesso → redirect (throws — Next captura).
 * - Validação inválida → redirect pra ?error=... (mostrado pelo searchParams
 *   no page.tsx).
 * - Erro de API → throw (error boundary do segmento captura).
 */
export async function createAgenteAction(formData: FormData): Promise<void> {
  const slug = slugify(String(formData.get("slug") || "").trim());
  const nome = String(formData.get("nome") || "").trim();
  const descricao = String(formData.get("descricao") || "").trim() || null;
  const template_catalog =
    String(formData.get("template_catalog") || "").trim() || "vsa_tech";

  if (!slug || !nome) {
    redirect("/agents/new?error=" + encodeURIComponent("Slug e nome são obrigatórios."));
  }
  if (slug.length < 2) {
    redirect(
      "/agents/new?error=" +
        encodeURIComponent(
          "Slug inválido: use ao menos 2 caracteres começando com letra (ex: vendas-sp)."
        )
    );
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
