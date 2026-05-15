"use server";

import { revalidatePath } from "next/cache";

import {
  addEmpresaMember,
  getMemberDepartamentos,
  getMemberPerfis,
  removeEmpresaMember,
  setMemberDepartamentos,
  setMemberPerfis,
  setMemberStatus,
  updateMemberRole,
  type UserStatus,
} from "@/lib/api";
import { auth, authPool } from "@/lib/auth";

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

type ResetLinkResult =
  | { ok: true; link: string; expiresAt: string }
  | { ok: false; error: string };

/**
 * Gera link de reset de senha pra um user.
 *
 * Sem SMTP: dispara o flow do Better Auth (`requestPasswordReset`), que
 * chama o callback `sendResetPassword` definido em lib/auth.ts. O
 * callback persiste o link em `auth.password_reset_pending`, então
 * lemos a row recém-criada e devolvemos pro admin copiar/colar.
 *
 * O link expira em 1h. Cada nova chamada substitui o anterior (UPSERT).
 */
export async function generateResetLinkAction(
  userId: string
): Promise<ResetLinkResult> {
  try {
    // 1. Resolver email do user (Better Auth requer email)
    const userRow = await authPool.query<{ email: string }>(
      `SELECT email FROM auth."user" WHERE id = $1`,
      [userId]
    );
    const email = userRow.rows[0]?.email;
    if (!email) {
      return { ok: false, error: "User não encontrado." };
    }

    // 2. Disparar flow de reset — callback `sendResetPassword` persiste
    //    em auth.password_reset_pending automaticamente.
    await auth.api.requestPasswordReset({
      body: { email, redirectTo: "/reset-password" },
    });

    // 3. Buscar link recém-persistido.
    const linkRow = await authPool.query<{
      url: string;
      expires_at: Date;
    }>(
      `SELECT url, expires_at FROM auth.password_reset_pending WHERE user_id = $1`,
      [userId]
    );
    const row = linkRow.rows[0];
    if (!row) {
      return {
        ok: false,
        error: "Link não foi gerado. Verifique config Better Auth.",
      };
    }

    return {
      ok: true,
      link: row.url,
      expiresAt: row.expires_at.toISOString(),
    };
  } catch (e) {
    return {
      ok: false,
      error:
        e instanceof Error ? e.message : "Erro ao gerar link de reset.",
    };
  }
}


// ============================================================
// Sprint Governança RBAC — atribuição perfis/deptos por member
// ============================================================

export async function getMemberPerfisAction(
  empresaId: number,
  userId: string
): Promise<{ ok: true; perfil_ids: number[] } | { ok: false; error: string }> {
  try {
    const r = await getMemberPerfis(empresaId, userId);
    return { ok: true, perfil_ids: r.perfil_ids };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar perfis.",
    };
  }
}

export async function setMemberPerfisAction(
  empresaId: number,
  userId: string,
  perfilIds: number[]
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await setMemberPerfis(empresaId, userId, perfilIds);
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar perfis.",
    };
  }
}

export async function getMemberDepartamentosAction(
  empresaId: number,
  userId: string
): Promise<
  | { ok: true; departamento_ids: number[] }
  | { ok: false; error: string }
> {
  try {
    const r = await getMemberDepartamentos(empresaId, userId);
    return { ok: true, departamento_ids: r.departamento_ids };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao carregar departamentos.",
    };
  }
}

export async function setMemberDepartamentosAction(
  empresaId: number,
  userId: string,
  departamentoIds: number[]
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await setMemberDepartamentos(empresaId, userId, departamentoIds);
    revalidatePath(`/companies/${empresaId}/members`);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao salvar departamentos.",
    };
  }
}
