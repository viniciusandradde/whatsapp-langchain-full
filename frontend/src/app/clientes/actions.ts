"use server";

import { revalidatePath } from "next/cache";

import {
  addClienteAnotacao,
  addClienteTag,
  removeClienteTag,
} from "@/lib/api";

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
