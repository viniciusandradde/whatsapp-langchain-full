"use server";

import { revalidatePath } from "next/cache";

import {
  applyTagsAtendimento,
  attachAtendimentoAba,
  claimAtendimento,
  closeAtendimento,
  createAba,
  createTag,
  criarNotaInterna,
  deleteAba,
  deleteTag,
  getAtendimentoMensagens,
  getClienteAtendimentosAnteriores,
  getContadoresAtendimento,
  getDepartamentos,
  getEmpresaAtendentes,
  getModelosMensagem,
  getMyAbas,
  getTags,
  getTagsAtendimento,
  marcarAtendimentoLido,
  reorderAbas,
  resetAtendimentoThread,
  responderAtendimento,
  transferAtendimento,
  transferAtendimentoParaDepartamento,
  updateAba,
  updateTag,
  type Aba,
  type AtendenteStatus,
  type Atendimento,
  type AtendimentoMensagem,
  type AtendimentoTag,
  type ContadoresAtendimento,
  type Departamento,
  type ModeloMensagem,
  type Tag,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };
type MensagensResult =
  | { ok: true; mensagens: AtendimentoMensagem[] }
  | { ok: false; error: string };
type ResponderResult =
  | { ok: true; mensagem: AtendimentoMensagem }
  | { ok: false; error: string };
type ModelosResult =
  | { ok: true; modelos: ModeloMensagem[] }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function loadMensagensAction(
  atendimentoId: number
): Promise<MensagensResult> {
  try {
    const data = await getAtendimentoMensagens(atendimentoId);
    return { ok: true, mensagens: data.mensagens };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadModelosAction(): Promise<ModelosResult> {
  try {
    const data = await getModelosMensagem();
    return { ok: true, modelos: data.modelos };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function responderAction(
  atendimentoId: number,
  conteudo: string
): Promise<ResponderResult> {
  const trimmed = conteudo.trim();
  if (!trimmed) return { ok: false, error: "Mensagem vazia." };
  try {
    const data = await responderAtendimento(atendimentoId, trimmed);
    revalidatePath("/atendimento");
    return { ok: true, mensagem: data.mensagem };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function claimAction(atendimentoId: number): Promise<Result> {
  try {
    await claimAtendimento(atendimentoId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function closeAction(
  atendimentoId: number,
  status: "resolvido" | "abandonado" = "resolvido"
): Promise<Result> {
  try {
    await closeAtendimento(atendimentoId, status);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function transferAction(
  atendimentoId: number,
  userId: string
): Promise<Result> {
  try {
    await transferAtendimento(atendimentoId, userId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function transferDepartamentoAction(
  atendimentoId: number,
  departamentoId: number
): Promise<Result> {
  try {
    await transferAtendimentoParaDepartamento(atendimentoId, departamentoId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type DepartamentosResult =
  | { ok: true; departamentos: Departamento[] }
  | { ok: false; error: string };

export async function loadDepartamentosAction(): Promise<DepartamentosResult> {
  try {
    const r = await getDepartamentos();
    return { ok: true, departamentos: r.departamentos.filter((d) => d.ativo) };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type AtendentesOnlineResult =
  | { ok: true; atendentes: AtendenteStatus[] }
  | { ok: false; error: string };

export async function loadAtendentesOnlineAction(): Promise<AtendentesOnlineResult> {
  try {
    const r = await getEmpresaAtendentes();
    // Só ativos + status=online (excluindo offline/ausente/pausa).
    const online = r.atendentes.filter(
      (a) => a.is_active && a.atendente_status === "online"
    );
    return { ok: true, atendentes: online };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

type ResetResult =
  | { ok: true; rowsDeleted: number; threadId: string }
  | { ok: false; error: string };

export async function resetThreadAction(
  atendimentoId: number
): Promise<ResetResult> {
  try {
    const r = await resetAtendimentoThread(atendimentoId);
    return { ok: true, rowsDeleted: r.rows_deleted, threadId: r.thread_id };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Sprint Atendimento UX: abas pessoais + contadores ---

type AbasResult = { ok: true; abas: Aba[] } | { ok: false; error: string };
type AbaResult = { ok: true; aba: Aba } | { ok: false; error: string };
type ContadoresResult =
  | { ok: true; contadores: ContadoresAtendimento }
  | { ok: false; error: string };

export async function loadAbasAction(): Promise<AbasResult> {
  try {
    const r = await getMyAbas();
    return { ok: true, abas: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadContadoresAction(): Promise<ContadoresResult> {
  try {
    const r = await getContadoresAtendimento();
    return { ok: true, contadores: r };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createAbaAction(payload: {
  descricao: string;
  cor?: string | null;
  icone?: string | null;
}): Promise<AbaResult> {
  try {
    const aba = await createAba(payload);
    revalidatePath("/atendimento");
    return { ok: true, aba };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateAbaAction(
  abaId: number,
  payload: { descricao?: string; cor?: string | null; icone?: string | null }
): Promise<AbaResult> {
  try {
    const aba = await updateAba(abaId, payload);
    revalidatePath("/atendimento");
    return { ok: true, aba };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteAbaAction(abaId: number): Promise<Result> {
  try {
    await deleteAba(abaId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function reorderAbasAction(
  orderedIds: number[]
): Promise<Result> {
  try {
    await reorderAbas(orderedIds);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function attachAtendimentoAbaAction(
  atendimentoId: number,
  abaId: number | null
): Promise<Result> {
  try {
    await attachAtendimentoAba(atendimentoId, abaId);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Sprint Atendimento UX 1.2: Tags ---

type TagsResult = { ok: true; tags: Tag[] } | { ok: false; error: string };
type TagResult = { ok: true; tag: Tag } | { ok: false; error: string };
type AtendimentoTagsResult =
  | { ok: true; tags: AtendimentoTag[] }
  | { ok: false; error: string };

export async function loadTagsAction(
  onlyAtivos: boolean = true
): Promise<TagsResult> {
  try {
    const r = await getTags(onlyAtivos);
    return { ok: true, tags: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function createTagAction(payload: {
  nome: string;
  cor?: string | null;
  descricao?: string | null;
}): Promise<TagResult> {
  try {
    const tag = await createTag(payload);
    revalidatePath("/atendimento");
    revalidatePath("/tags");
    return { ok: true, tag };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function updateTagAction(
  tagId: number,
  payload: {
    nome?: string;
    cor?: string | null;
    descricao?: string | null;
    ativo?: boolean;
  }
): Promise<TagResult> {
  try {
    const tag = await updateTag(tagId, payload);
    revalidatePath("/atendimento");
    revalidatePath("/tags");
    return { ok: true, tag };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteTagAction(tagId: number): Promise<Result> {
  try {
    await deleteTag(tagId);
    revalidatePath("/atendimento");
    revalidatePath("/tags");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function loadTagsAtendimentoAction(
  atendimentoId: number
): Promise<AtendimentoTagsResult> {
  try {
    const r = await getTagsAtendimento(atendimentoId);
    return { ok: true, tags: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function applyTagsAtendimentoAction(
  atendimentoId: number,
  delta: { add: number[]; remove: number[] }
): Promise<Result> {
  try {
    await applyTagsAtendimento(atendimentoId, delta);
    revalidatePath("/atendimento");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Sprint 1.3: notas internas + read receipts ---

type NotaResult =
  | { ok: true; mensagem: AtendimentoMensagem }
  | { ok: false; error: string };

export async function criarNotaInternaAction(
  atendimentoId: number,
  texto: string
): Promise<NotaResult> {
  const t = texto.trim();
  if (!t) return { ok: false, error: "Nota vazia." };
  try {
    const r = await criarNotaInterna(atendimentoId, t);
    revalidatePath("/atendimento");
    // Backend retorna shape parcial — adapta pro tipo da timeline
    const mensagem: AtendimentoMensagem = {
      id: r.id,
      agent_id: "manual",
      incoming_message: "",
      media_url: null,
      media_type: null,
      normalized_input: null,
      media_processing_status: null,
      response: r.response,
      status: "done",
      created_at: r.created_at,
      processed_at: r.created_at,
      media_processing_error: null,
      error: null,
      interna: true,
      criado_por_user_id: r.criado_por_user_id,
    };
    return { ok: true, mensagem };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function marcarAtendimentoLidoAction(
  atendimentoId: number
): Promise<Result> {
  try {
    await marcarAtendimentoLido(atendimentoId);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

// --- Sprint 1.4: histórico do cliente no painel ---

type HistoricoResult =
  | { ok: true; atendimentos: Atendimento[] }
  | { ok: false; error: string };

export async function loadClienteHistoricoAction(
  clienteId: number,
  options: { excludeId?: number; limit?: number } = {}
): Promise<HistoricoResult> {
  try {
    const r = await getClienteAtendimentosAnteriores(clienteId, options);
    return { ok: true, atendimentos: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
