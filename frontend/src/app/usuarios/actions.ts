"use server";

import { revalidatePath } from "next/cache";

import { friendlyError } from "@/lib/api-error-shared";
import { upsertUserPassword } from "@/lib/user-password";
import { auth, authPool } from "@/lib/auth";
import {
  atualizarUsuario,
  criarUsuario,
  enviarConviteUsuario,
  deletarUsuario,
  getConexoes,
  getDepartamentos,
  getEmpresaAtendentes,
  getPerfis,
  getUsuarioAtividade,
  invalidarSessionsUsuario,
  listUsuarios,
  replicarUsuario,
  setAtendenteMaxParalelos,
  setStatusUsuario,
  type AtendenteStatus,
  type AtividadeEvento,
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

export interface ConviteResultado {
  ok: boolean;
  telefone?: string;
  erro?: string;
}

/**
 * Envia no WhatsApp do usuário um link de uso único para ELE criar a senha.
 *
 * O link nasce aqui no Next (só o Better Auth gera token que ele mesmo
 * aceita: `requestPasswordReset` → callback `sendResetPassword` persiste em
 * `auth.password_reset_pending`, mig 025) e o WhatsApp sai do FastAPI (só o
 * backend tem `build_outbound_client`). Esta action é a ponte.
 *
 * O link NÃO volta para a tela nem entra em log — quem tem o link define a
 * senha da conta. A tela só recebe {ok, telefone|erro}.
 */
export async function enviarConviteAction(
  userId: string
): Promise<ConviteResultado> {
  try {
    // 1. Email do user (Better Auth exige email pro flow de reset).
    const userRow = await authPool.query<{ email: string | null }>(
      `SELECT email FROM auth."user" WHERE id = $1`,
      [userId]
    );
    const email = userRow.rows[0]?.email;
    if (!email) {
      return {
        ok: false,
        erro: "Usuário sem e-mail — o link de acesso precisa de um e-mail.",
      };
    }

    // 2. Dispara o flow de reset — o callback persiste o link.
    await auth.api.requestPasswordReset({
      body: { email, redirectTo: "/reset-password" },
    });

    // 3. Lê o link recém-persistido (UPSERT: sempre o mais novo).
    const linkRow = await authPool.query<{ url: string; expires_at: Date }>(
      `SELECT url, expires_at FROM auth.password_reset_pending
        WHERE user_id = $1`,
      [userId]
    );
    const row = linkRow.rows[0];
    if (!row) {
      return { ok: false, erro: "O link de acesso não foi gerado." };
    }

    // 4. Backend envia no WhatsApp. 200 com ok:false = motivo legível.
    const r = await enviarConviteUsuario(userId, {
      link: row.url,
      expira_em: row.expires_at.toISOString(),
    });
    if (r.ok) revalidatePath("/usuarios");
    return { ok: r.ok, telefone: r.telefone, erro: r.erro };
  } catch (e) {
    return { ok: false, erro: _err(e) };
  }
}

export async function criarUsuarioAction(
  body: UsuarioCreateInput,
  opts?: { enviarConvite?: boolean }
): Promise<
  | { ok: true; usuario: Usuario; password: string; convite?: ConviteResultado }
  | { ok: false; error: string }
> {
  try {
    // 1. Cria user em backend (Better Auth.user + membership + perfis + deptos)
    const u = await criarUsuario(body);

    // 2. Gera senha + persiste hash em auth.account (providerId='credential')
    // A senha continua existindo MESMO com convite: é o plano B quando o
    // WhatsApp não sai (sem telefone, sem conexão, provedor fora).
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

    // 3. Convite por WhatsApp (opt-in do form). Falha aqui NÃO desfaz nada:
    // o resultado viaja pra modal explicar e cair no plano B da senha.
    let convite: ConviteResultado | undefined;
    if (opts?.enviarConvite && body.telefone) {
      convite = await enviarConviteAction(u.id);
    }

    revalidatePath("/usuarios");
    return { ok: true, usuario: u, password, convite };
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
      console.error("[usuarios] avatar upload", resp.status, errText.slice(0, 300));
      return { ok: false, error: friendlyError(resp.status, errText) };
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

export async function loadAtividadeAction(
  userId: string
): Promise<Result<AtividadeEvento[]>> {
  try {
    const r = await getUsuarioAtividade(userId);
    return { ok: true, data: r.items };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}
