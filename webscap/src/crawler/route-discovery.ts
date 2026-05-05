/**
 * Descoberta automática de rotas via DOM walk: extrai href de <a>,
 * data-routerlink/[routerLink] (Angular) e role="link" no menu lateral.
 *
 * Filtra: somente rotas internas (mesma origem), normaliza trailing
 * slash, descarta query/hash. Limita profundidade pra não escapar do
 * dashboard.
 */

import type { Page } from "playwright";

import { log } from "../lib/logger.js";

export const STATIC_ROUTES_FALLBACK = [
  "/dashboard/panel",
  "/dashboard/sistema/usuario",
  "/dashboard/cliente",
  "/dashboard/atendimento",
  "/dashboard/conexao",
  "/dashboard/calendario",
  "/dashboard/hk/hook",
  "/dashboard/cp/campanha",
  "/dashboard/ia",
  "/dashboard/arquivo",
];

export interface DiscoveryOptions {
  /** Rota inicial pra walk. Default '/dashboard'. */
  seedRoute?: string;
  /** Limite hard. Default 60 rotas (suficiente pra qualquer SaaS razoável). */
  maxRoutes?: number;
  /** Prefixo obrigatório (filtra fora landing/marketing). Default '/dashboard'. */
  pathPrefix?: string;
}

export async function discoverRoutes(
  page: Page,
  baseUrl: string,
  opts: DiscoveryOptions = {},
): Promise<string[]> {
  const seedRoute = opts.seedRoute ?? "/dashboard";
  const maxRoutes = opts.maxRoutes ?? 60;
  const pathPrefix = opts.pathPrefix ?? "/dashboard";

  await page.goto(baseUrl + seedRoute, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  // Pequena pausa pra menu lateral renderizar (Angular hydrate, lazy loaders)
  await page.waitForTimeout(1500);

  const hrefs = await page.evaluate(({ origin, prefix, max }) => {
    const found = new Set<string>();
    const candidates: HTMLElement[] = [];

    document.querySelectorAll("a[href]").forEach((a) => {
      candidates.push(a as HTMLElement);
    });
    document
      .querySelectorAll("[routerLink], [data-routerlink], [routerlink]")
      .forEach((el) => candidates.push(el as HTMLElement));

    for (const el of candidates) {
      let raw =
        el.getAttribute("href") ||
        el.getAttribute("routerLink") ||
        el.getAttribute("routerlink") ||
        el.getAttribute("data-routerlink") ||
        "";
      if (!raw) continue;
      // Resolve absolute → path
      try {
        const url = new URL(raw, origin);
        if (url.origin !== origin) continue;
        let p = url.pathname;
        // Normaliza
        p = p.replace(/\/+$/, "") || "/";
        // Filtra fora landing
        if (!p.startsWith(prefix)) continue;
        // Descarta IDs numéricos (não vamos visitar /cliente/123)
        if (/\/\d+(\/|$)/.test(p)) continue;
        found.add(p);
        if (found.size >= max) break;
      } catch {
        /* href inválido — ignora */
      }
    }
    return [...found];
  }, { origin: baseUrl, prefix: pathPrefix, max: maxRoutes });

  const sorted = hrefs.sort();
  log.info("routes_discovered_dom", {
    total: sorted.length,
    seedRoute,
    sample: sorted.slice(0, 5),
  });
  return sorted;
}
