"use server";

import { revalidatePath } from "next/cache";

import {
  addEmpresaMember,
  getMemberDepartamentos,
  getMemberPerfis,
  getUsuario,
  removeEmpresaMember,
  setMemberDepartamentos,
  setMemberPerfis,
  setMemberStatus,
  updateMemberRole,
  type UserStatus,
} from "@/lib/api";
import { auth, authPool } from "@/lib/auth";
import { upsertUserPassword } from "@/lib/user-password";

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
    // Autorização: herda o gate do backend (require_permission +
    // escopo de empresa) — 403/404 se o chamador não pode gerenciar o alvo.
    await getUsuario(userId);
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

/**
 * Reseta senha do user via servidor: backend gera senha aleatória forte
 * com CSPRNG, aplica via Better Auth (resetPassword com token consumido
 * imediatamente), e retorna a senha em texto pro admin compartilhar
 * pelo canal seguro que preferir.
 *
 * Por que NO SERVIDOR (não admin digita): evita exposição da senha em
 * histórico do navegador, autocomplete, screen-share, gerenciador de
 * senhas com cache, etc. Senha aparece UMA VEZ na resposta — admin
 * copia, manda, e fecha. Backend nunca persiste plaintext (só hash
 * scrypt do Better Auth em auth.account).
 *
 * Pra desativar/forçar logout simultâneo: combine com setMemberStatus.
 */
export async function resetMemberPasswordAction(
  userId: string
): Promise<
  | { ok: true; password: string; email: string | null }
  | { ok: false; error: string }
> {
  try {
    // Autorização: herda o gate do backend (require_permission +
    // escopo de empresa) — 403/404 se o chamador não pode gerenciar o alvo.
    // Sem isto, a action reseta senha de qualquer user cross-tenant.
    await getUsuario(userId);
    // Sprint U.4 — FIX: busca por user_id, não filtra por email NOT NULL.
    // Users criados via /usuarios sem email têm email sintético
    // (`user-{uuid}@no-email.local`) — funcionam pra reset normal.
    // Quando email é NULL de verdade (corner case), ainda assim
    // setUserPassword aceita userId direto.
    const userRow = await authPool.query<{ id: string; email: string | null }>(
      `SELECT id, email FROM auth."user" WHERE id = $1`,
      [userId]
    );
    if (userRow.rows.length === 0) {
      return { ok: false, error: "Usuário não encontrado." };
    }
    const email = userRow.rows[0].email;

    // 1. Gera senha aleatória forte no servidor (16 chars, sem ambiguidade)
    const newPassword = generateSecurePassword(16);

    // 2. Persiste hash via helper (mesma rotina usada em /usuarios) — não
    // depende do admin plugin do Better Auth e funciona pra user sem email.
    await upsertUserPassword(userId, newPassword);

    // 3. Invalida sessions ativas (força re-login)
    await authPool.query(`DELETE FROM auth.session WHERE "userId" = $1`, [
      userId,
    ]);

    return { ok: true, password: newPassword, email };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "Erro ao redefinir senha.",
    };
  }
}


function generateSecurePassword(len = 16): string {
  // Alfabeto sem ambiguidade visual (sem 0/O, 1/l/I) + símbolos seguros
  const chars =
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%&*";
  // Node 20+: crypto.getRandomValues disponível globalmente
  const arr = new Uint8Array(len);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => chars[b % chars.length]).join("");
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
