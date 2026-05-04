"use server";

import { revalidatePath } from "next/cache";

import {
  addEmpresaMember,
  removeEmpresaMember,
  setMemberStatus,
  updateMemberRole,
  type UserStatus,
} from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

const VALID_ROLES = ["admin", "operator", "viewer"] as const;
type Role = (typeof VALID_ROLES)[number];

function asRole(value: string): Role | null {
  return (VALID_ROLES as readonly string[]).includes(value)
    ? (value as Role)
    : null;
}

export async function addMemberAction(
  empresaId: number,
  formData: FormData
): Promise<Result> {
  try {
    const userId = String(formData.get("user_id") || "").trim();
    const role = asRole(String(formData.get("role") || "operator"));
    if (!userId) return { ok: false, error: "user_id é obrigatório." };
    if (!role) return { ok: false, error: "Role inválido." };
    await addEmpresaMember(empresaId, { user_id: userId, role });
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao adicionar membro.",
    };
  }
}

export async function changeMemberRoleAction(
  empresaId: number,
  userId: string,
  newRole: string
): Promise<Result> {
  try {
    const role = asRole(newRole);
    if (!role) return { ok: false, error: "Role inválido." };
    await updateMemberRole(empresaId, userId, role);
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao mudar role.",
    };
  }
}

export async function removeMemberAction(
  empresaId: number,
  userId: string
): Promise<Result> {
  try {
    await removeEmpresaMember(empresaId, userId);
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao remover membro.",
    };
  }
}

export async function setMemberStatusAction(
  empresaId: number,
  userId: string,
  status: UserStatus
): Promise<Result> {
  try {
    await setMemberStatus(empresaId, userId, status);
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao mudar status.",
    };
  }
}
