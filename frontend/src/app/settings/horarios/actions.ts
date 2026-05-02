"use server";

import { revalidatePath } from "next/cache";

import {
  createFeriado,
  createHorario,
  deleteFeriado,
  deleteHorario,
  type Feriado,
  type FeriadoInput,
  type HorarioFuncionamento,
  type HorarioFuncionamentoInput,
} from "@/lib/api";

type SaveHorarioResult =
  | { ok: true; horario: HorarioFuncionamento }
  | { ok: false; error: string };

type SaveFeriadoResult =
  | { ok: true; feriado: Feriado }
  | { ok: false; error: string };

type Result = { ok: true } | { ok: false; error: string };

function toError(e: unknown): string {
  return e instanceof Error ? e.message : "Erro desconhecido.";
}

export async function saveHorarioAction(
  formData: FormData
): Promise<SaveHorarioResult> {
  try {
    const dia = Number(formData.get("dia_semana"));
    const ini = String(formData.get("hora_inicio") || "");
    const fim = String(formData.get("hora_fim") || "");
    if (!ini || !fim) {
      return { ok: false, error: "Hora de início e fim são obrigatórias." };
    }
    if (fim <= ini) {
      return {
        ok: false,
        error: "Hora de fim deve ser maior que hora de início.",
      };
    }
    const input: HorarioFuncionamentoInput = {
      dia_semana: dia,
      hora_inicio: ini,
      hora_fim: fim,
      ativo: true,
    };
    const horario = await createHorario(input);
    revalidatePath("/settings/horarios");
    return { ok: true, horario };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteHorarioAction(id: number): Promise<Result> {
  try {
    await deleteHorario(id);
    revalidatePath("/settings/horarios");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function saveFeriadoAction(
  formData: FormData
): Promise<SaveFeriadoResult> {
  try {
    const data = String(formData.get("data") || "").trim();
    if (!data) return { ok: false, error: "Data é obrigatória." };
    const input: FeriadoInput = {
      data,
      descricao:
        (String(formData.get("descricao") || "").trim() || null) as
          | string
          | null,
    };
    const feriado = await createFeriado(input);
    revalidatePath("/settings/horarios");
    return { ok: true, feriado };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}

export async function deleteFeriadoAction(id: number): Promise<Result> {
  try {
    await deleteFeriado(id);
    revalidatePath("/settings/horarios");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: toError(e) };
  }
}
