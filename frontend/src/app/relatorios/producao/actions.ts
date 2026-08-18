"use server";

import {
  gerarRelatorioProducao,
  getPainelProducao,
  saveConfigProducao,
  type ConfigProducao,
  type PainelProducao,
} from "@/lib/api";

type Resultado<T> = { ok: true; data: T } | { ok: false; error: string };

/**
 * `apiFetch` já traduz o erro para a frase pt-BR que o backend mandou em
 * `detail`. Aqui só resta o fallback de quando nem isso existe.
 */
function msg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export async function loadPainelAction(): Promise<Resultado<PainelProducao>> {
  try {
    return { ok: true, data: await getPainelProducao() };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível carregar os relatórios.") };
  }
}

export async function gerarAction(): Promise<
  Resultado<{ ja_existia: boolean }>
> {
  try {
    const r = await gerarRelatorioProducao();
    return { ok: true, data: { ja_existia: r.ja_existia } };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível pedir o relatório.") };
  }
}

export async function salvarConfigAction(
  cfg: ConfigProducao
): Promise<Resultado<true>> {
  try {
    await saveConfigProducao(cfg);
    return { ok: true, data: true };
  } catch (e) {
    return { ok: false, error: msg(e, "Não foi possível salvar o agendamento.") };
  }
}
