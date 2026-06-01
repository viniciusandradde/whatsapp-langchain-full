"use server";

import { revalidatePath } from "next/cache";

import {
  atualizarTurno,
  criarTurno,
  deletarTurno,
  getTurnoUsers,
  listTurnos,
  listUsuarios,
  setTurnoUsers,
  type Turno,
  type TurnoInput,
} from "@/lib/api";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function _err(e: unknown): string {
  return e instanceof Error ? e.message : String(e ?? "Erro desconhecido");
}

export async function loadTurnosAction(): Promise<Result<Turno[]>> {
  try {
    const r = await listTurnos();
    return { ok: true, data: r.items };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function criarTurnoAction(
  body: TurnoInput
): Promise<Result<Turno>> {
  try {
    const t = await criarTurno(body);
    revalidatePath("/settings/turnos");
    return { ok: true, data: t };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function atualizarTurnoAction(
  id: number,
  body: Partial<TurnoInput>
): Promise<Result<Turno>> {
  try {
    const t = await atualizarTurno(id, body);
    revalidatePath("/settings/turnos");
    return { ok: true, data: t };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function deletarTurnoAction(id: number): Promise<Result<void>> {
  try {
    await deletarTurno(id);
    revalidatePath("/settings/turnos");
    return { ok: true, data: undefined };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function loadTurnoUsersAction(
  id: number
): Promise<Result<{ assigned: string[]; all: { id: string; nome: string | null }[] }>> {
  try {
    const [usersR, allR] = await Promise.all([
      getTurnoUsers(id),
      listUsuarios({ status: "active", limit: 500 }),
    ]);
    return {
      ok: true,
      data: {
        assigned: usersR.users.map((u) => u.id),
        all: allR.items.map((u) => ({ id: u.id, nome: u.nome })),
      },
    };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}

export async function setTurnoUsersAction(
  id: number,
  userIds: string[]
): Promise<Result<void>> {
  try {
    await setTurnoUsers(id, userIds);
    revalidatePath("/settings/turnos");
    return { ok: true, data: undefined };
  } catch (e) {
    return { ok: false, error: _err(e) };
  }
}
