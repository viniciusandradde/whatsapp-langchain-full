"use server";

import { revalidatePath } from "next/cache";

import {
  addClienteAnotacao,
  addClienteTag,
  classificarCliente,
  createCliente,
  getCliente,
  removeClienteTag,
  type Cliente,
  type ClassificacaoInput,
  type ClienteCreateInput,
} from "@/lib/api";
import { ApiRequestError } from "@/lib/api-error-shared";

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function addAnotacaoAction(
  clienteId: number,
  conteudo: string
): Promise<Result> {
  const trimmed = conteudo.trim();
  if (!trimmed) {
    return { ok: false, error: "Anotação não pode ficar vazia." };
  }
  try {
    await addClienteAnotacao(clienteId, trimmed);
    revalidatePath(`/clientes/${clienteId}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function addTagAction(
  clienteId: number,
  tag: string
): Promise<Result> {
  const trimmed = tag.trim();
  if (!trimmed) {
    return { ok: false, error: "Tag não pode ficar vazia." };
  }
  try {
    await addClienteTag(clienteId, trimmed);
    revalidatePath(`/clientes/${clienteId}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function removeTagAction(
  clienteId: number,
  tag: string
): Promise<Result> {
  try {
    await removeClienteTag(clienteId, tag);
    revalidatePath(`/clientes/${clienteId}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export type CriarClienteResult =
  | { ok: true; id: number }
  | { ok: false; error: string; existenteId?: number };

export async function criarClienteAction(
  body: ClienteCreateInput
): Promise<CriarClienteResult> {
  try {
    const c = await createCliente(body);
    revalidatePath("/clientes");
    return { ok: true, id: c.id };
  } catch (e) {
    // 409: telefone já cadastrado — a tela oferece abrir o cadastro existente.
    if (e instanceof ApiRequestError && e.status === 409) {
      const d = e.detail as { cliente_id?: unknown } | null;
      const existenteId = typeof d?.cliente_id === "number" ? d.cliente_id : undefined;
      return { ok: false, error: e.message, existenteId };
    }
    return { ok: false, error: toError(e) };
  }
}

export async function classificarClienteAction(
  clienteId: number,
  body: ClassificacaoInput
): Promise<{ ok: true; cliente: Cliente } | { ok: false; error: string }> {
  try {
    const cliente = await classificarCliente(clienteId, body);
    revalidatePath(`/clientes/${clienteId}`);
    revalidatePath("/clientes");
    return { ok: true, cliente };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

/** Cliente para o bloco de classificação no painel da conversa. */
export async function carregarClienteAction(
  clienteId: number
): Promise<{ ok: true; cliente: Cliente } | { ok: false; error: string }> {
  try {
    const { cliente } = await getCliente(clienteId);
    return { ok: true, cliente };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
