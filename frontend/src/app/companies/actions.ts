"use server";

import { revalidatePath } from "next/cache";

import { friendlyError } from "@/lib/api-error-shared";
import { auth } from "@/lib/auth";
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
type SaveResult =
  | { ok: true; empresaId: number }
  | { ok: false; error: string };

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
): Promise<SaveResult> {
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
    // White-label (mig 115)
    const branding = {
      nome_exibicao: _str(formData, "nome_exibicao"),
      cor_primaria: _str(formData, "cor_primaria"),
      cor_secundaria: _str(formData, "cor_secundaria"),
    };

    let savedId: number;
    if (empresaId) {
      const update: EmpresaUpdateInput = {
        nome,
        slug,
        plano,
        doc,
        ...fiscal,
        ...branding,
      };
      const status = (formData.get("status") as string) || null;
      if (status) update.status = status;
      await updateEmpresa(empresaId, update);
      savedId = empresaId;
    } else {
      const input: EmpresaInput = { nome, slug, plano, doc, ...fiscal };
      const created = await createEmpresa(input);
      savedId = created.id;
      // Branding na criação aplica via update (create endpoint não recebe).
      if (branding.nome_exibicao || branding.cor_primaria || branding.cor_secundaria) {
        await updateEmpresa(savedId, branding);
      }
    }
    revalidatePath("/companies");
    revalidatePath("/", "layout");
    return { ok: true, empresaId: savedId };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro desconhecido.",
    };
  }
}

export async function uploadEmpresaLogoAction(
  empresaId: number,
  formData: FormData
): Promise<Result> {
  try {
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return { ok: false, error: "Arquivo não enviado." };
    }
    const { cookies, headers: nextHeaders } = await import("next/headers");
    const session = await auth.api.getSession({ headers: await nextHeaders() });
    if (!session?.user?.id) {
      return { ok: false, error: "Sessão expirada. Faça login novamente." };
    }
    const empresaCookie = (await cookies()).get("active_empresa_id")?.value;
    const apiUrl =
      process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "";
    const serviceToken = process.env.INTERNAL_SERVICE_TOKEN || "";
    const reqHeaders: Record<string, string> = {
      Authorization: `Bearer ${serviceToken}`,
      "X-User-Id": session.user.id,
    };
    if (empresaCookie) reqHeaders["X-Empresa-Id"] = empresaCookie;

    const fd = new FormData();
    fd.set("file", file);
    const resp = await fetch(`${apiUrl}/api/empresas/${empresaId}/logo`, {
      method: "POST",
      headers: reqHeaders,
      body: fd,
    });
    if (!resp.ok) {
      const t = await resp.text();
      console.error("[companies] logo upload", resp.status, t.slice(0, 300));
      return { ok: false, error: friendlyError(resp.status, t) };
    }
    revalidatePath("/companies");
    revalidatePath("/", "layout");
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
