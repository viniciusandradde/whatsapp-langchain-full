"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";

import { getMyEmpresas } from "@/lib/api";

const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

/**
 * Server Action: troca a empresa ativa no cookie.
 *
 * Valida que o usuário é membro (ou superadmin) consultando GET
 * /api/empresas — quem não tem permissão não vê a empresa na lista.
 * O empresa default (is_default=TRUE) já vem preselecionado na próxima
 * navegação se nenhum cookie for encontrado.
 */
export async function setActiveEmpresa(
  empresaId: number
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const { empresas } = await getMyEmpresas();
    const allowed = empresas.some((e) => e.id === empresaId);
    if (!allowed) {
      return { ok: false, error: "Empresa fora da lista de membership." };
    }

    const cookieStore = await cookies();
    cookieStore.set(ACTIVE_EMPRESA_COOKIE, String(empresaId), {
      path: "/",
      httpOnly: false,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 dias
    });

    revalidatePath("/", "layout");
    return { ok: true };
  } catch (e) {
    const error =
      e instanceof Error ? e.message : "Falha ao trocar empresa ativa.";
    return { ok: false, error };
  }
}
