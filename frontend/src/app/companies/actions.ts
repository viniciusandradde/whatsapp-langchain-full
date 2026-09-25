"use server";

import { revalidatePath } from "next/cache";

import { friendlyError } from "@/lib/api-error-shared";
import { auth } from "@/lib/auth";
import {
  createEmpresa,
  getEmpresaCsat,
  getPagamentosEmpresa,
  registrarPagamento,
  setEmpresaVigencia,
  updateEmpresa,
  updateEmpresaCsat,
  type PagamentoInput,
  type PagamentoRegistrado,
  type PagamentosEmpresa,
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

export async function loadResumoDiarioAction(empresaId: number): Promise<
  | { ok: true; config: import("@/lib/api").EmpresaResumoDiarioConfig }
  | { ok: false; error: string }
> {
  try {
    const { getEmpresaResumoDiario } = await import("@/lib/api");
    return { ok: true, config: await getEmpresaResumoDiario(empresaId) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function saveResumoDiarioAction(
  empresaId: number,
  body: import("@/lib/api").EmpresaResumoDiarioConfig
): Promise<
  | { ok: true; config: import("@/lib/api").EmpresaResumoDiarioConfig }
  | { ok: false; error: string }
> {
  try {
    const { updateEmpresaResumoDiario } = await import("@/lib/api");
    return { ok: true, config: await updateEmpresaResumoDiario(empresaId, body) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function testarResumoDiarioAction(
  empresaId: number
): Promise<{ ok: boolean; error: string | null }> {
  try {
    const { testarEmpresaResumoDiario } = await import("@/lib/api");
    const r = await testarEmpresaResumoDiario(empresaId);
    return { ok: r.ok, error: r.erro };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function loadPlanosCatalogoAction(): Promise<
  | { ok: true; data: import("@/lib/api").PlanoCatalogo[] }
  | { ok: false; error: string }
> {
  try {
    const { getPlanosCatalogo } = await import("@/lib/api");
    const { items } = await getPlanosCatalogo();
    return { ok: true, data: items };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar planos.",
    };
  }
}

export async function reativarEmpresaAction(
  empresaId: number
): Promise<Result> {
  try {
    await updateEmpresa(empresaId, { status: "active" });
    revalidatePath("/companies");
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao reativar a empresa.",
    };
  }
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

    // Mig 147: política de atendimento. Checkbox ausente = false, que é o
    // default (assumir em silêncio).
    const atendimento = {
      anuncia_atendente_assumiu: formData.get("anuncia_atendente_assumiu") === "on",
    };

    // Retenção de dados (mig 185): dias; 0 = ilimitado.
    const retencaoRaw = formData.get("retencao_dias");
    const retencaoDias =
      retencaoRaw === null || retencaoRaw === "" ? null : Number(retencaoRaw);

    let savedId: number;
    if (empresaId) {
      const update: EmpresaUpdateInput = {
        nome,
        slug,
        plano,
        doc,
        ...fiscal,
        ...branding,
        ...atendimento,
      };
      if (retencaoDias !== null && !Number.isNaN(retencaoDias)) {
        update.retencao_dias = retencaoDias;
      }
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

// --- Voz do agente (mig 176) ---

/** Salva só os 3 campos de voz — o PUT /api/empresas/{id} é patch parcial,
 * então nada além da voz é tocado. */
export async function saveEmpresaVozAction(
  empresaId: number,
  body: Pick<EmpresaUpdateInput, "voz_ativa" | "voz_nome" | "voz_estilo">
): Promise<Result> {
  try {
    await updateEmpresa(empresaId, body);
    revalidatePath("/companies");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

/**
 * Superadmin fixa ou limpa (`null` = sem vencimento) o último dia do plano
 * pago (ADR-005 leva E). A lista de empresas é revalidada porque é dela que
 * o form lê a data.
 */
export async function setVigenciaAction(
  empresaId: number,
  planoValidoAte: string | null
): Promise<Result> {
  try {
    await setEmpresaVigencia(empresaId, planoValidoAte);
    revalidatePath("/companies");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

/** Histórico de pagamentos + sugestão do próximo período (leva F). */
export async function loadPagamentosAction(
  empresaId: number
): Promise<{ ok: true; data: PagamentosEmpresa } | { ok: false; error: string }> {
  try {
    return { ok: true, data: await getPagamentosEmpresa(empresaId) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

/** Superadmin registra um pagamento conciliado no gateway (leva F). */
export async function registrarPagamentoAction(
  empresaId: number,
  body: PagamentoInput
): Promise<{ ok: true; data: PagamentoRegistrado } | { ok: false; error: string }> {
  try {
    const data = await registrarPagamento(empresaId, body);
    revalidatePath("/companies");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

/** Gera a amostra de áudio da voz escolhida (sem persistir nada). */
export async function previewEmpresaVozAction(
  empresaId: number,
  vozNome: string,
  vozEstilo: string
): Promise<
  | { ok: true; audioBase64: string; mime: string }
  | { ok: false; error: string }
> {
  try {
    const { previewEmpresaVoz } = await import("@/lib/api");
    const r = await previewEmpresaVoz(empresaId, {
      voz_nome: vozNome,
      voz_estilo: vozEstilo,
    });
    return { ok: true, audioBase64: r.audio_base64, mime: r.mime };
  } catch (e) {
    return {
      ok: false,
      error:
        e instanceof Error ? e.message : "Erro ao gerar a amostra de voz.",
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

// --- Chave da OpenRouter por empresa (ADR-007, mig 204) ---

type ChaveOpenRouterResult =
  | { ok: true; data: import("@/lib/api").OpenRouterChaveStatus }
  | { ok: false; error: string };

export async function loadOpenRouterChaveAction(
  empresaId: number
): Promise<ChaveOpenRouterResult> {
  try {
    const { getEmpresaOpenRouterChave } = await import("@/lib/api");
    return { ok: true, data: await getEmpresaOpenRouterChave(empresaId) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

/** A chave só passa por aqui a caminho da API — nunca é guardada nem logada no Next. */
export async function setOpenRouterChaveAction(
  empresaId: number,
  chave: string
): Promise<ChaveOpenRouterResult> {
  try {
    const { setEmpresaOpenRouterChave } = await import("@/lib/api");
    return { ok: true, data: await setEmpresaOpenRouterChave(empresaId, chave.trim()) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function removerOpenRouterChaveAction(
  empresaId: number
): Promise<ChaveOpenRouterResult> {
  try {
    const { removerEmpresaOpenRouterChave } = await import("@/lib/api");
    return { ok: true, data: await removerEmpresaOpenRouterChave(empresaId) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function provisionarOpenRouterChaveAction(
  empresaId: number,
  limiteUsd: number | null
): Promise<ChaveOpenRouterResult> {
  try {
    const { provisionarEmpresaOpenRouterChave } = await import("@/lib/api");
    return { ok: true, data: await provisionarEmpresaOpenRouterChave(empresaId, limiteUsd) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}

export async function setLimiteOpenRouterChaveAction(
  empresaId: number,
  limiteUsd: number | null
): Promise<ChaveOpenRouterResult> {
  try {
    const { setLimiteEmpresaOpenRouterChave } = await import("@/lib/api");
    return { ok: true, data: await setLimiteEmpresaOpenRouterChave(empresaId, limiteUsd) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Erro." };
  }
}
