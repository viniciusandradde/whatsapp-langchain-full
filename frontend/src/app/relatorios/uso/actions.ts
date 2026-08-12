"use server";

import {
  enviarRelatorioUso,
  getClientesUso,
  getConfigUso,
  getRelatorioUso,
  saveConfigUso,
  type ClienteUso,
  type ConfigUso,
  type RelatorioUso,
} from "@/lib/api";

type Resultado<T> = { ok: true; data: T } | { ok: false; error: string };

/**
 * `apiFetch` já traduz o erro para a frase pt-BR que o backend mandou em
 * `detail`, sem detalhe técnico. Aqui só resta o fallback de quando nem isso
 * existe (rede caiu antes da resposta).
 */
function msg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export async function loadClientesAction(): Promise<Resultado<ClienteUso[]>> {
  try {
    const r = await getClientesUso();
    return { ok: true, data: r.clientes };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível listar os clientes.") };
  }
}

export async function loadRelatorioAction(
  empresaId: number,
  competencia: string
): Promise<Resultado<RelatorioUso>> {
  try {
    return { ok: true, data: await getRelatorioUso(empresaId, competencia) };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível montar o relatório.") };
  }
}

/**
 * Dispara o PDF no WhatsApp do cliente.
 *
 * O endpoint devolve 200 com `ok: false` quando o provedor recusa — a falha é
 * do WhatsApp, não da nossa API, e o motivo precisa chegar em texto na tela.
 */
export async function enviarAction(
  empresaId: number,
  competencia: string,
  telefone?: string
): Promise<Resultado<{ competencia: string }>> {
  try {
    const r = await enviarRelatorioUso(empresaId, { competencia, telefone });
    if (!r.ok) return { ok: false, error: r.erro || "O envio não foi aceito." };
    return { ok: true, data: { competencia: r.competencia } };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível enviar o relatório.") };
  }
}

export async function loadConfigAction(
  empresaId: number
): Promise<Resultado<ConfigUso>> {
  try {
    return { ok: true, data: await getConfigUso(empresaId) };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível ler o agendamento.") };
  }
}

export async function saveConfigAction(
  empresaId: number,
  body: Partial<ConfigUso>
): Promise<Resultado<ConfigUso>> {
  try {
    return { ok: true, data: await saveConfigUso(empresaId, body) };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível salvar o agendamento.") };
  }
}
