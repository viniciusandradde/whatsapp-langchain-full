"use server";

import { revalidatePath } from "next/cache";

import {
  createEmpresa,
  getEmpresaCsat,
  updateEmpresa,
  updateEmpresaCsat,
  type EmpresaCsatConfig,
  type EmpresaInput,
  type EmpresaUpdateInput,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

type CsatResult =
  | { ok: true; config: EmpresaCsatConfig }
  | { ok: false; error: string };

function _str(formData: FormData, key: string): string | null {
  const v = String(formData.get(key) || "").trim();
  return v || null;
}

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
    const doc = _str(formData, "doc");

    // Campos fiscais + endereço (opcionais)
    const fiscal = {
      razao_social: _str(formData, "razao_social"),
      inscricao_estadual: _str(formData, "inscricao_estadual"),
      endereco_fiscal_cep: _str(formData, "endereco_fiscal_cep"),
      endereco_fiscal_logradouro: _str(formData, "endereco_fiscal_logradouro"),
      endereco_fiscal_numero: _str(formData, "endereco_fiscal_numero"),
      endereco_fiscal_complemento: _str(formData, "endereco_fiscal_complemento"),
      endereco_fiscal_bairro: _str(formData, "endereco_fiscal_bairro"),
      endereco_fiscal_cidade: _str(formData, "endereco_fiscal_cidade"),
      endereco_fiscal_uf: _str(formData, "endereco_fiscal_uf"),
    };

    if (empresaId) {
      const update: EmpresaUpdateInput = { nome, slug, plano, doc, ...fiscal };
      const status = (formData.get("status") as string) || null;
      if (status) update.status = status;
      await updateEmpresa(empresaId, update);
    } else {
      const input: EmpresaInput = { nome, slug, plano, doc, ...fiscal };
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

export async function loadEmpresaCsatAction(
  empresaId: number
): Promise<CsatResult> {
  try {
    const config = await getEmpresaCsat(empresaId);
    return { ok: true, config };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro" };
  }
}

export async function saveEmpresaCsatAction(
  empresaId: number,
  body: EmpresaCsatConfig
): Promise<CsatResult> {
  try {
    const config = await updateEmpresaCsat(empresaId, body);
    revalidatePath("/companies");
    return { ok: true, config };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro" };
  }
}
