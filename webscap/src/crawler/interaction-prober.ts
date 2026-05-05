/**
 * Sondagem de mutations sem efeito colateral.
 *
 * Estratégia:
 * 1. Lista todos os botões / forms visíveis na página.
 * 2. Pra cada botão "abrir modal" (geralmente disparam GET, não mutation),
 *    clica e fecha (Escape).
 * 3. Captura QUALQUER GraphQL request disparada nesse processo.
 *
 * **NÃO** clica em botões que match patterns destrutivos (Salvar/Excluir/
 * Confirmar/Disparar/Enviar...). Mesmo defaults do flow runner.
 *
 * Resultado: mutations descobertas mesmo sem flow YAML específico.
 */

import type { Page } from "playwright";

import { log } from "../lib/logger.js";

const DESTRUCTIVE_RE =
  /(salvar|salvando|excluir|deletar|remover|confirmar|enviar|disparar|publicar|aprovar|rejeitar|sair|logout)/i;

/** Texto/aria que indica "abrir algo" — seguro pra clicar. */
const SAFE_OPEN_RE =
  /(novo|nova|adicionar|criar|abrir|filtro|filtros|configurar|editar|visualizar|expandir|detalhes|mais)/i;

export interface ProbeOptions {
  page: Page;
  /** Limite de botões clicados por página pra não explodir tempo. */
  maxClicksPerPage?: number;
  /** ms entre clicks pra dar tempo da modal abrir/fechar. */
  intervalMs?: number;
}

export async function probeInteractions(opts: ProbeOptions): Promise<{
  triggered: number;
  skipped: number;
}> {
  const max = opts.maxClicksPerPage ?? 8;
  const interval = opts.intervalMs ?? 1200;
  let triggered = 0;
  let skipped = 0;

  // Coleta candidatos
  const candidates = await opts.page.evaluate(({ openRe, destrRe }) => {
    const open = new RegExp(openRe, "i");
    const destr = new RegExp(destrRe, "i");
    const buttons = Array.from(
      document.querySelectorAll(
        "button, a[role='button'], [role='button'], .p-button",
      ),
    ) as HTMLElement[];
    const safe: { selector: string; label: string }[] = [];
    for (const b of buttons) {
      const label = (b.innerText || b.getAttribute("aria-label") || "").trim();
      if (!label) continue;
      if (destr.test(label)) continue;
      if (!open.test(label)) continue;
      // Selector estável aproximado: data-test/id/aria-label
      const dt =
        b.getAttribute("data-test") ||
        b.getAttribute("data-testid") ||
        b.id ||
        b.getAttribute("aria-label");
      const sel = dt
        ? `[data-test="${dt}"], [data-testid="${dt}"], [aria-label="${dt}"], #${dt}`
        : `text="${label.slice(0, 30)}"`;
      safe.push({ selector: sel, label: label.slice(0, 40) });
    }
    return safe.slice(0, 20);
  }, { openRe: SAFE_OPEN_RE.source, destrRe: DESTRUCTIVE_RE.source });

  log.debug("probe_candidates", { count: candidates.length });

  for (const c of candidates.slice(0, max)) {
    try {
      await opts.page
        .locator(c.selector.split(",")[0]!)
        .first()
        .click({ timeout: 2000, force: false });
      triggered += 1;
      await opts.page.waitForTimeout(interval);
      // Tenta fechar modal/dropdown abertos
      await opts.page.keyboard.press("Escape").catch(() => {});
      await opts.page.waitForTimeout(300);
    } catch {
      skipped += 1;
    }
  }

  log.info("probe_done", { triggered, skipped });
  return { triggered, skipped };
}
