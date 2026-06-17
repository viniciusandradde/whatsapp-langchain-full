"use server";

import { revalidatePath } from "next/cache";

import { auth } from "@/lib/auth";
import {
  abortCampanha,
  addCampanhaDestinatarios,
  clonarCampanha,
  createCampanha,
  dispatchCampanha,
  getCampanha,
  getCampanhaDestinatarios,
  getTags,
  listTemplates,
  previewCrmCampanha,
  removeCampanhaDestinatario,
  updateCampanha,
  type Campanha,
  type CampanhaCreateInput,
  type CampanhaDestinatario,
  type PreviewCrmFiltro,
  type Tag,
  type WabaTemplate,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };
type OkResult = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function loadTagsAction(): Promise<Result<Tag[]>> {
  try {
    const { items } = await getTags();
    return { ok: true, data: items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function previewCrmAction(
  filtro: PreviewCrmFiltro
): Promise<Result<{ total: number; telefones: string[] }>> {
  try {
    const data = await previewCrmCampanha(filtro);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateCampanhaAction(
  id: number,
  body: Partial<CampanhaCreateInput> & { agendar?: boolean }
): Promise<Result<Campanha>> {
  try {
    const data = await updateCampanha(id, body);
    revalidatePath(`/campanhas/${id}`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function addDestinatariosAction(
  id: number,
  body: { telefones?: string[]; crm?: PreviewCrmFiltro }
): Promise<Result<{ novos: number; total: number }>> {
  try {
    const data = await addCampanhaDestinatarios(id, body);
    revalidatePath(`/campanhas/${id}`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function removeDestinatarioAction(
  id: number,
  destId: number
): Promise<Result<{ removido: boolean; total: number }>> {
  try {
    const data = await removeCampanhaDestinatario(id, destId);
    revalidatePath(`/campanhas/${id}`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function clonarCampanhaAction(
  id: number
): Promise<Result<Campanha>> {
  try {
    const data = await clonarCampanha(id);
    revalidatePath("/campanhas");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createCampanhaAction(
  body: CampanhaCreateInput
): Promise<Result<Campanha>> {
  try {
    const c = await createCampanha(body);
    revalidatePath("/campanhas");
    return { ok: true, data: c };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function uploadCampanhaMediaAction(
  formData: FormData
): Promise<Result<{ media_url: string; media_tipo: string }>> {
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
    const reqHeaders: Record<string, string> = {
      Authorization: `Bearer ${process.env.INTERNAL_SERVICE_TOKEN || ""}`,
      "X-User-Id": session.user.id,
    };
    if (empresaCookie) reqHeaders["X-Empresa-Id"] = empresaCookie;
    const fd = new FormData();
    fd.set("file", file);
    const resp = await fetch(`${apiUrl}/api/campanhas/upload-media`, {
      method: "POST",
      headers: reqHeaders,
      body: fd,
    });
    if (!resp.ok) {
      return {
        ok: false,
        error: `Falha no upload (${resp.status}): ${(await resp.text()).slice(0, 200)}`,
      };
    }
    return {
      ok: true,
      data: (await resp.json()) as { media_url: string; media_tipo: string },
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadApprovedTemplatesAction(
  conexaoId: number
): Promise<Result<WabaTemplate[]>> {
  try {
    const r = await listTemplates(conexaoId);
    return {
      ok: true,
      data: r.templates.filter((t) => t.status === "approved"),
    };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function dispatchCampanhaAction(id: number): Promise<OkResult> {
  try {
    await dispatchCampanha(id);
    revalidatePath("/campanhas");
    revalidatePath(`/campanhas/${id}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function abortCampanhaAction(id: number): Promise<OkResult> {
  try {
    await abortCampanha(id);
    revalidatePath("/campanhas");
    revalidatePath(`/campanhas/${id}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// Wrappers server-side pra polling em Client Component
// (não pode importar @/lib/api direto porque ele puxa server-only).
export async function refreshCampanhaAction(
  id: number
): Promise<
  | { ok: true; campanha: Campanha; destinatarios: CampanhaDestinatario[] }
  | { ok: false; error: string }
> {
  try {
    const [campanha, dest] = await Promise.all([
      getCampanha(id),
      getCampanhaDestinatarios(id),
    ]);
    return { ok: true, campanha, destinatarios: dest.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
