/**
 * Health check do storageState — detecta sessão expirada antes de
 * gastar 5min crawling com 401 disfarçado.
 *
 * Estratégia: hit numa rota protegida, observa redirect ou status.
 * - Se a URL final volta pro login (ex: ?redirect=/dashboard) → expirou
 * - Se fetch direto numa op GraphQL retorna 401 → expirou
 * - Se OK → sessão viva
 */

import fs from "node:fs";

import type { Page } from "playwright";

import { log } from "../lib/logger.js";

export interface SessionGuardOptions {
  baseUrl: string;
  graphqlPath: string;
  storageFile: string;
  /** Rota usada pra ping. Default = `/dashboard`. */
  pingRoute?: string;
  /** Padrão de URL que indica login page (regex). */
  loginUrlPattern?: RegExp;
}

export interface SessionStatus {
  alive: boolean;
  reason?: string;
}

export function ensureStorageFileExists(storageFile: string): void {
  if (!fs.existsSync(storageFile)) {
    throw new Error(
      `Storage state '${storageFile}' não existe. Rode 'npm run login' primeiro.`,
    );
  }
}

export async function checkSession(
  page: Page,
  opts: SessionGuardOptions,
): Promise<SessionStatus> {
  const route = opts.pingRoute ?? "/dashboard";
  const loginPattern = opts.loginUrlPattern ?? /\/(login|signin|auth)/i;

  // 1) Ping HTTP via fetch direto na API (não navega) — barato
  const pingResp = await page.evaluate(
    async ({ url }) => {
      try {
        const r = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            query: "query Ping { __typename }",
          }),
        });
        return { status: r.status };
      } catch (e) {
        return { status: 0, error: String(e) };
      }
    },
    { url: opts.graphqlPath },
  );

  if (pingResp.status === 401 || pingResp.status === 403) {
    return { alive: false, reason: `GraphQL ping retornou ${pingResp.status}` };
  }

  // 2) Navegação rápida — confere se redireciona pro login
  try {
    await page.goto(opts.baseUrl + route, {
      waitUntil: "domcontentloaded",
      timeout: 15_000,
    });
  } catch (e) {
    log.warn("session_guard_nav_failed", { error: String(e) });
    return { alive: false, reason: `nav falhou: ${String(e).slice(0, 100)}` };
  }

  if (loginPattern.test(page.url())) {
    return {
      alive: false,
      reason: `redirecionou pra login: ${page.url()}`,
    };
  }

  return { alive: true };
}
