"use server";

import { revalidatePath } from "next/cache";

import {
  updateCliente,
  type Cliente,
  type ClienteUpdateInput,
} from "@/lib/api";

type Result =
  | { ok: true; cliente: Cliente }
  | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function updateClienteAction(
  id: number,
  patch: ClienteUpdateInput
): Promise<Result> {
  try {
    const cliente = await updateCliente(id, patch);
    revalidatePath(`/clientes/${id}`);
    return { ok: true, cliente };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
