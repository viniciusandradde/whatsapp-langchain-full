"use server";

import { revalidatePath } from "next/cache";

import { upsertUserPassword } from "@/lib/user-password";
import { auth } from "@/lib/auth";
import {
  atualizarUsuario,
  criarUsuario,
  deletarUsuario,
  getConexoes,
  getDepartamentos,
  getEmpresaAtendentes,
  getPerfis,
  invalidarSessionsUsuario,
  listUsuarios,
  replicarUsuario,
  setAtendenteMaxParalelos,
  setStatusUsuario,
  type AtendenteStatus,
  type SetStatusUsuarioBody,
  type Usuario,
  type UsuarioCreateInput,
  type UsuariosListResult,
  type UsuarioUpdateInput,
} from "@/lib/api";

export interface PerfilOption {
  id: number;
  nome: string;
  is_system: boolean;
}

export interface DepartamentoOption {
  id: number;
  nome: string;
}

export interface ConexaoOption {
  id: number;
  nome: string;
  provider: string;
}

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function _err(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e ?? "Erro desconhecido");
}

function _generatePassword(length = 16): string {
  // Alphabet sem ambiguidade (sem 0/O, 1/l/I) — copia generateSecurePassword
  const chars =
    "ABCDEFGHJKLMNPQRSTUVWXYZ" +
    "abcdefghijkmnpqrstuvwxyz" +
    "23456789" +
    "!@#$%&*";
  let pw = "";
  const buf = new Uint8Array(length);
  crypto.getRandomValues(buf);
  for (let i = 0; i < length; i++) {
    pw += chars[buf[i] % chars.length];
  }
  return pw;
}

export async function loadUsuariosAction(params: {
  search?: string;
  perfil_id?: number;
  departamento_id?: number;
  status?: "active" | "disabled";
  limit?: number;
  offset?: number;
} = {}): Promise<Result<UsuariosListResult>> {
  try {
    const r = await listUsuarios(params);
    return { ok: true, data: r };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function criarUsuarioAction(
  body: UsuarioCreateInput
): Promise<
  | { ok: true; usuario: Usuario; password: string }
  | { ok: false; error: string }
> {
  try {
    // 1. Cria user em backend (Better Auth.user + membership + perfis + deptos)
    const u = await criarUsuario(body);

    // 2. Gera senha + persiste hash em auth.account (providerId='credential')
    const password = _generatePassword(16);
    try {
      await upsertUserPassword(u.id, password);
    } catch (e) {
      return {
        ok: false,
        error:
          "Usuário criado, mas falha ao gravar senha. " +
          "Use 'Resetar senha' no editor pra tentar de novo. Detalhe: " +
          _err(e),
      };
    }

    revalidatePath("/usuarios");
    return { ok: true, usuario: u, password };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function atualizarUsuarioAction(
  userId: string,
  body: UsuarioUpdateInput
): Promise<Result<Usuario>> {
  try {
    const u = await atualizarUsuario(userId, body);
    revalidatePath("/usuarios");
    return { ok: true, data: u };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function resetarSenhaUsuarioAction(
  userId: string
): Promise<
  | { ok: true; password: string }
  | { ok: false; error: string }
> {
  try {
    const password = _generatePassword(16);
    await upsertUserPassword(userId, password);
    // Invalida sessions ativas — força re-login com senha nova
    await invalidarSessionsUsuario(userId);
    return { ok: true, password };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function uploadAvatarAction(
  userId: string,
  formData: FormData
): Promise<Result<{ avatar_path: string }>> {
  try {
    // Upload de avatar é multipart — não dá pra usar apiFetch JSON.
    // Chama API diretamente via env API_URL + service token.
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return { ok: false, error: "Arquivo não enviado." };
    }

    const { cookies, headers: nextHeaders } = await import("next/headers");
    const sessionHeaders = await nextHeaders();
    const session = await auth.api.getSession({ headers: sessionHeaders });
    if (!session?.user?.id) {
      return { ok: false, error: "Sessão expirada. Faça login novamente." };
    }
    const empresaCookie = (await cookies()).get("active_empresa_id")?.value;

    const apiUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "";
    const serviceToken = process.env.INTERNAL_SERVICE_TOKEN || "";
    const reqHeaders: Record<string, string> = {
      Authorization: `Bearer ${serviceToken}`,
      "X-User-Id": session.user.id,
    };
    if (empresaCookie) reqHeaders["X-Empresa-Id"] = empresaCookie;

    const fd = new FormData();
    fd.set("file", file);

    const resp = await fetch(`${apiUrl}/api/usuarios/${userId}/avatar`, {
      method: "POST",
      headers: reqHeaders,
      body: fd,
    });
    if (!resp.ok) {
      const errText = await resp.text();
      return {
        ok: false,
        error: `API error ${resp.status}: ${errText.slice(0, 200)}`,
      };
    }
    const data = (await resp.json()) as { avatar_path: string };
    revalidatePath("/usuarios");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadPerfisOptionsAction(): Promise<
  Result<PerfilOption[]>
> {
  try {
    const r = await getPerfis();
    return {
      ok: true,
      data: r.items.map((p) => ({
        id: p.id,
        nome: p.nome,
        is_system: p.is_system,
      })),
    };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadDepartamentosOptionsAction(): Promise<
  Result<DepartamentoOption[]>
> {
  try {
    const r = await getDepartamentos();
    return {
      ok: true,
      data: r.departamentos
        .filter((d) => d.ativo)
        .map((d) => ({ id: d.id, nome: d.nome })),
    };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function setStatusUsuarioAction(
  userId: string,
  body: SetStatusUsuarioBody
): Promise<Result<{ status: string; transferidos: number }>> {
  try {
    // Endpoint nativo PATCH /api/usuarios/{id}/status (transferência ao
    // desativar embutida). Não usa mais o legado /membros/{id}/status.
    const r = await setStatusUsuario(userId, body);
    revalidatePath("/usuarios");
    return { ok: true, data: r };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function removerUsuarioAction(
  userId: string
): Promise<Result<void>> {
  try {
    await deletarUsuario(userId);
    revalidatePath("/usuarios");
    return { ok: true, data: undefined };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function clonarUsuarioAction(
  origemUserId: string,
  body: { nome: string; email?: string | null; telefone?: string | null }
): Promise<
  | { ok: true; usuario: Usuario; password: string }
  | { ok: false; error: string }
> {
  try {
    // Clona perfis+deptos+conexões+role+capacidade (replicar) e em seguida
    // gera a senha pelo mesmo fluxo do create.
    const u = await replicarUsuario(origemUserId, body);
    const password = _generatePassword(16);
    try {
      await upsertUserPassword(u.id, password);
    } catch (e) {
      return {
        ok: false,
        error:
          "Usuário clonado, mas falha ao gravar senha. " +
          "Use 'Resetar senha' no editor. Detalhe: " +
          _err(e),
      };
    }
    revalidatePath("/usuarios");
    return { ok: true, usuario: u, password };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function setMaxParalelosAction(
  userId: string,
  maxParalelos: number
): Promise<Result<void>> {
  try {
    await setAtendenteMaxParalelos(userId, maxParalelos);
    revalidatePath("/usuarios");
    return { ok: true, data: undefined };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadConexoesOptionsAction(): Promise<
  Result<ConexaoOption[]>
> {
  try {
    const r = await getConexoes();
    return {
      ok: true,
      data: r.conexoes.map((c) => ({
        id: c.id,
        nome: c.display_name || c.from_number || `Conexão ${c.id}`,
        provider: c.provider,
      })),
    };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadAtendentesAction(): Promise<Result<AtendenteStatus[]>> {
  try {
    const r = await getEmpresaAtendentes();
    return { ok: true, data: r.atendentes };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}
