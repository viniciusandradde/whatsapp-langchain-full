"use server";

import { revalidatePath } from "next/cache";

import {
  createEmpresa,
  updateEmpresa,
  type EmpresaInput,
  type EmpresaUpdateInput,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

export async function saveEmpresa(
  empresaId: number | null,
  formData: FormData
): Promise<Result> {
  try {
    const nome = String(formData.get("nome") || "").trim();
    const slug = String(formData.get("slug") || "").trim();
    if (!nome || !slug) {
      return { ok: false, error: "Nome e slug são obrigatórios." };
    }
    const plano = String(formData.get("plano") || "free");
    const doc = (formData.get("doc") as string) || null;

    if (empresaId) {
      const update: EmpresaUpdateInput = { nome, slug, plano, doc };
      const status = (formData.get("status") as string) || null;
      if (status) update.status = status;
      await updateEmpresa(empresaId, update);
    } else {
      const input: EmpresaInput = { nome, slug, plano, doc };
      await createEmpresa(input);
    }
    revalidatePath("/companies");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro desconhecido.",
    };
  }
}
