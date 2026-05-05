/**
 * Executor de flows declarativos. Recebe FlowDefinition + Page Playwright,
 * roda steps sequencialmente, captura artefatos.
 *
 * Safety: por default bloqueia clicks em selectors que match a regex
 * de "ações destrutivas" (Salvar/Excluir/Confirmar). Sem isso, rodar
 * um flow contra prod podia mutar dados reais.
 */

import path from "node:path";

import type { Page } from "playwright";

import { log } from "../lib/logger.js";
import { sleep } from "../lib/retry.js";
import type {
  FlowDefinition,
  FlowResult,
  FlowStep,
  WaitArg,
} from "./types.js";

const DEFAULT_SAFE_BLOCK_RE =
  /(salvar|salvando|excluir|deletar|remover|confirmar|enviar|disparar|publicar|aprovar|rejeitar|cancelar.*atendimento)/i;

export interface RunFlowOptions {
  page: Page;
  baseUrl: string;
  /** Onde salvar screenshots tirados pelo flow. */
  screenshotsDir: string;
  /** Onde salvar payloads marcados. */
  payloadsDir: string;
  /** Default 30s. */
  defaultTimeoutMs?: number;
  /** Quando match em capture_payload, conteúdo bruto da response salvo aqui. */
  graphqlPath: string;
}

export async function runFlow(
  flow: FlowDefinition,
  opts: RunFlowOptions,
): Promise<FlowResult> {
  const startedAt = Date.now();
  const safeMode = flow.safe_mode !== false;
  const blockPatterns = (flow.safe_mode_block ?? []).map(
    (p) => new RegExp(p, "i"),
  );
  const allBlock = [DEFAULT_SAFE_BLOCK_RE, ...blockPatterns];

  const payloadsCaptured: string[] = [];
  const screenshotsCaptured: string[] = [];

  // Cache de TODAS as ops vistas — capture_payload busca aqui primeiro
  // (pra resolver o caso onde a request já passou antes do step armar
  // o listener). Se não tiver no cache, instala listener pra próxima.
  type CachedPayload = { request: unknown; response: unknown };
  const seenPayloads = new Map<string, CachedPayload>();
  const pendingCaptures = new Map<
    string,
    (payload: CachedPayload) => void
  >();

  const onResponse = async (res: import("playwright").Response) => {
    if (!res.url().includes(opts.graphqlPath)) return;
    try {
      const reqBody = res.request().postData();
      const reqJson = reqBody ? JSON.parse(reqBody) : {};
      const opName = reqJson.operationName as string | undefined;
      if (!opName) return;
      const respBody = await res.json().catch(() => null);
      const payload: CachedPayload = { request: reqJson, response: respBody };
      // Sempre guarda no cache (mais recente vence — tudo bem, normalmente
      // é o mesmo shape pra mesma op)
      seenPayloads.set(opName, payload);
      const cb = pendingCaptures.get(opName);
      if (cb) {
        pendingCaptures.delete(opName);
        cb(payload);
      }
    } catch {
      /* ignora */
    }
  };
  opts.page.on("response", onResponse);

  let stepsRun = 0;
  try {
    for (const step of flow.steps) {
      await runStep(step, {
        page: opts.page,
        baseUrl: opts.baseUrl,
        defaultTimeoutMs: opts.defaultTimeoutMs ?? 30_000,
        safeMode,
        blockPatterns: allBlock,
        screenshotsDir: opts.screenshotsDir,
        payloadsDir: opts.payloadsDir,
        seenPayloads,
        flowName: flow.name,
        screenshotsCaptured,
        payloadsCaptured,
        pendingCaptures,
      });
      stepsRun++;
    }
    return {
      name: flow.name,
      ok: true,
      durationMs: Date.now() - startedAt,
      stepsRun,
      stepsTotal: flow.steps.length,
      payloadsCaptured,
      screenshotsCaptured,
    };
  } catch (e) {
    return {
      name: flow.name,
      ok: false,
      durationMs: Date.now() - startedAt,
      stepsRun,
      stepsTotal: flow.steps.length,
      payloadsCaptured,
      screenshotsCaptured,
      errorMessage: String(e).slice(0, 300),
      errorAtStep: stepsRun,
    };
  } finally {
    opts.page.off("response", onResponse);
  }
}

interface StepCtx {
  page: Page;
  baseUrl: string;
  defaultTimeoutMs: number;
  safeMode: boolean;
  blockPatterns: RegExp[];
  screenshotsDir: string;
  payloadsDir: string;
  flowName: string;
  screenshotsCaptured: string[];
  payloadsCaptured: string[];
  seenPayloads: Map<string, { request: unknown; response: unknown }>;
  pendingCaptures: Map<
    string,
    (payload: { request: unknown; response: unknown }) => void
  >;
}

async function runStep(step: FlowStep, ctx: StepCtx): Promise<void> {
  const fs = await import("node:fs");

  if ("goto" in step) {
    const url = step.goto.startsWith("http")
      ? step.goto
      : ctx.baseUrl + step.goto;
    log.debug("flow_goto", { url });
    await ctx.page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: ctx.defaultTimeoutMs,
    });
    if (step.wait) {
      await applyWait(step.wait, ctx);
    } else {
      // Pequena pausa pra Angular hydratar
      await ctx.page.waitForTimeout(800);
    }
    return;
  }

  if ("click" in step) {
    const sel = step.click;
    if (
      ctx.safeMode &&
      !step.safe_mode_bypass &&
      ctx.blockPatterns.some((p) => p.test(sel))
    ) {
      throw new Error(
        `safe_mode bloqueou click em "${sel}" — adicione safe_mode_bypass: true se intencional`,
      );
    }
    log.debug("flow_click", { sel });
    // Selectors com vírgula são lista de fallbacks: tenta cada um até
    // achar. Permite YAML mais resiliente: 'text="X", [role="tab"]:has-text("X")'
    const selectors = sel.includes(",") && !sel.includes("[")
      ? sel.split(",").map((s) => s.trim()).filter(Boolean)
      : [sel];
    const timeout = step.timeout_ms ?? Math.min(ctx.defaultTimeoutMs, 10_000);
    let clicked = false;
    let lastErr: unknown;
    for (const s of selectors) {
      try {
        await ctx.page.click(s, { timeout });
        clicked = true;
        break;
      } catch (e) {
        lastErr = e;
      }
    }
    if (!clicked) {
      const optional = step.optional !== false; // default true em flows de exploração
      if (optional) {
        log.warn("flow_click_skipped", { sel, error: String(lastErr).slice(0, 100) });
        return;
      }
      throw lastErr;
    }
    return;
  }

  if ("fill" in step) {
    log.debug("flow_fill", { sel: step.fill });
    await ctx.page.fill(step.fill, step.with, {
      timeout: ctx.defaultTimeoutMs,
    });
    return;
  }

  if ("select" in step) {
    log.debug("flow_select", { sel: step.select, option: step.option });
    // Tenta <select> nativo primeiro; cai pro click no PrimeNG dropdown
    try {
      await ctx.page.selectOption(step.select, step.option, {
        timeout: 3000,
      });
    } catch {
      await ctx.page.click(step.select);
      await ctx.page.click(`text="${step.option}"`, {
        timeout: ctx.defaultTimeoutMs,
      });
    }
    return;
  }

  if ("wait" in step) {
    await applyWait(step.wait, ctx);
    return;
  }

  if ("wait_for" in step) {
    log.debug("flow_wait_for", { sel: step.wait_for });
    try {
      await ctx.page.waitForSelector(step.wait_for, {
        timeout: step.timeout_ms ?? ctx.defaultTimeoutMs,
      });
    } catch (e) {
      if (step.optional !== false) {
        log.warn("flow_wait_for_skipped", { sel: step.wait_for });
        return;
      }
      throw e;
    }
    return;
  }

  if ("screenshot" in step) {
    const safe = step.screenshot.replace(/[^A-Za-z0-9_-]/g, "_");
    const file = path.join(
      ctx.screenshotsDir,
      `flow_${ctx.flowName}__${safe}.png`,
    );
    await ctx.page.screenshot({ path: file, fullPage: true });
    ctx.screenshotsCaptured.push(file);
    log.debug("flow_screenshot", { file });
    return;
  }

  if ("capture_payload" in step) {
    const opName = step.capture_payload;
    const timeout = step.timeout_ms ?? 5_000;

    function savePayload(payload: { request: unknown; response: unknown }) {
      const file = path.join(
        ctx.payloadsDir,
        `flow_${ctx.flowName}__${opName}.json`,
      );
      fs.writeFileSync(file, JSON.stringify(payload, null, 2));
      ctx.payloadsCaptured.push(file);
      log.info("flow_payload_captured", { opName, file });
    }

    // 1) Cache hit — request já passou antes (caso comum de op disparada
    //    no goto que precede esse step). Sai sem esperar.
    const cached = ctx.seenPayloads.get(opName);
    if (cached) {
      savePayload(cached);
      return;
    }

    // 2) Não tem no cache — instala listener pra próxima request
    log.debug("flow_capture_arming", { opName, timeout });
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        ctx.pendingCaptures.delete(opName);
        // Não-fatal: warn + segue. capture_payload é "best effort".
        log.warn("flow_capture_timeout", { opName, timeout });
        resolve();
      }, timeout);
      ctx.pendingCaptures.set(opName, (payload) => {
        clearTimeout(timer);
        savePayload(payload);
        resolve();
      });
    });
    return;
  }

  if ("assert_route" in step) {
    const url = ctx.page.url();
    if (!url.includes(step.assert_route)) {
      throw new Error(
        `assert_route falhou: esperado contém "${step.assert_route}", got "${url}"`,
      );
    }
    return;
  }

  if ("assert_text" in step) {
    const sel = step.selector ?? "body";
    const text = await ctx.page.textContent(sel, { timeout: 5_000 });
    if (!text || !text.includes(step.assert_text)) {
      throw new Error(
        `assert_text falhou em ${sel}: esperado "${step.assert_text}"`,
      );
    }
    return;
  }

  if ("press" in step) {
    if (step.selector) {
      await ctx.page.press(step.selector, step.press);
    } else {
      await ctx.page.keyboard.press(step.press);
    }
    return;
  }

  if ("hover" in step) {
    try {
      await ctx.page.hover(step.hover, {
        timeout: step.timeout_ms ?? 5_000,
      });
    } catch (e) {
      if (step.optional !== false) {
        log.warn("flow_hover_skipped", { sel: step.hover });
        return;
      }
      throw e;
    }
    return;
  }

  throw new Error(`step desconhecido: ${JSON.stringify(step)}`);
}

async function applyWait(arg: WaitArg, ctx: StepCtx): Promise<void> {
  if ("networkidle" in arg) {
    await ctx.page.waitForLoadState("networkidle", {
      timeout: arg.timeout_ms ?? ctx.defaultTimeoutMs,
    });
  } else if ("selector" in arg) {
    await ctx.page.waitForSelector(arg.selector, {
      timeout: arg.timeout_ms ?? ctx.defaultTimeoutMs,
    });
  } else if ("ms" in arg) {
    await sleep(arg.ms);
  }
}
