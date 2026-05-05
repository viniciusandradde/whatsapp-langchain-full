"use server";

import { revalidatePath } from "next/cache";

import {
  assignDepartamentoUser,
  createDepartamento,
  deleteDepartamento,
  getDepartamentoUsers,
  unassignDepartamentoUser,
  updateDepartamento,
  type Departamento,
  type DepartamentoInput,
  type DepartamentoUser,
} from "@/lib/api";

type SaveResult =
  | { ok: true; departamento: Departamento }
  | { ok: false; error: string };

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

function parseParentId(raw: FormDataEntryValue | null): number | null {
  const s = String(raw || "").trim();
  if (!s || s === "0") return null;
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export async function saveDepartamentoAction(
  formData: FormData
): Promise<SaveResult> {
  try {
    const idRaw = String(formData.get("id") || "").trim();
    const input: DepartamentoInput = {
      nome: String(formData.get("nome") || "").trim(),
      descricao:
        (String(formData.get("descricao") || "").trim() || null) as
          | string
          | null,
      ativo: formData.get("ativo") === "on",
      parent_id: parseParentId(formData.get("parent_id")),
    };
    if (!input.nome) return { ok: false, error: "Nome é obrigatório." };
    const departamento = idRaw
      ? await updateDepartamento(Number(idRaw), input)
      : await createDepartamento(input);
    revalidatePath("/settings/departamentos");
    return { ok: true, departamento };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteDepartamentoAction(
  id: number
): Promise<Result> {
  try {
    await deleteDepartamento(id);
    revalidatePath("/settings/departamentos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function listDepartamentoUsersAction(
  depId: number
): Promise<{ ok: true; items: DepartamentoUser[] } | { ok: false; error: string }> {
  try {
    const r = await getDepartamentoUsers(depId);
    return { ok: true, items: r.items };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function assignUserAction(
  depId: number,
  userId: string
): Promise<Result> {
  try {
    await assignDepartamentoUser(depId, userId.trim());
    revalidatePath("/settings/departamentos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function unassignUserAction(
  depId: number,
  userId: string
): Promise<Result> {
  try {
    await unassignDepartamentoUser(depId, userId);
    revalidatePath("/settings/departamentos");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
