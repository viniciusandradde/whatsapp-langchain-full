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

// Lista expandida cobrindo módulos top-level + sub-módulos sistema/IA/etc
// observados em runtime no schema-summary.md. Usada como fallback quando
// auto-discovery falha OU como sementes pra crawl multi-nível.
export const STATIC_ROUTES_FALLBACK = [
  // Core
  "/dashboard/panel",
  "/dashboard/cliente",
  "/dashboard/atendimento",
  "/dashboard/atendimento/historico",
  "/dashboard/conexao",
  "/dashboard/calendario",
  "/dashboard/arquivo",
  // Sistema
  "/dashboard/sistema/usuario",
  "/dashboard/sistema/departamento",
  "/dashboard/sistema/grupo-sistema",
  "/dashboard/sistema/empresa",
  "/dashboard/sistema/horario",
  "/dashboard/sistema/turno",
  "/dashboard/sistema/cidade",
  "/dashboard/sistema/log",
  // Hooks
  "/dashboard/hk/hook",
  "/dashboard/hk/hook/url",
  "/dashboard/hk/hook/task",
  // Campanhas
  "/dashboard/cp/campanha",
  "/dashboard/cp/template",
  "/dashboard/cp/waba",
  // IA
  "/dashboard/ia",
  "/dashboard/ia/agente",
  "/dashboard/ia/base-conhecimento",
  "/dashboard/ia/mcp",
  "/dashboard/ia/variavel",
  "/dashboard/ia/execucao",
  "/dashboard/ia/uso",
  // Misc
  "/dashboard/menu",
  "/dashboard/form",
  "/dashboard/aviso",
  "/dashboard/produto",
  "/dashboard/produto/categoria",
  "/dashboard/pedido",
  "/dashboard/transacao",
  "/dashboard/modelo-mensagem",
];

export interface DiscoveryOptions {
  /** Rota inicial pra walk. Default '/dashboard'. */
  seedRoute?: string;
  /** Limite hard. Default 100 rotas. */
  maxRoutes?: number;
  /** Prefixo obrigatório (filtra fora landing/marketing). Default '/dashboard'. */
  pathPrefix?: string;
  /** Profundidade do crawl recursivo. 1 = só sementes; 2 = sementes + descobertas; 3 = + sub-descobertas. */
  depth?: number;
  /** Sementes adicionais pra incluir antes do walk (mescla com discovery). */
  extraSeeds?: string[];
}

export async function discoverRoutes(
  page: Page,
  baseUrl: string,
  opts: DiscoveryOptions = {},
): Promise<string[]> {
  const seedRoute = opts.seedRoute ?? "/dashboard";
  const maxRoutes = opts.maxRoutes ?? 100;
  const pathPrefix = opts.pathPrefix ?? "/dashboard";
  const depth = Math.max(1, opts.depth ?? 2);

  const visited = new Set<string>();
  const found = new Set<string>();
  // Sementes iniciais: rota base + extras
  const queue: Array<{ route: string; level: number }> = [
    { route: seedRoute, level: 1 },
    ...(opts.extraSeeds ?? []).map((r) => ({ route: r, level: 1 })),
  ];

  while (queue.length > 0 && found.size < maxRoutes) {
    const item = queue.shift()!;
    if (visited.has(item.route)) continue;
    visited.add(item.route);

    let urlsHere: string[] = [];
    try {
      await page.goto(baseUrl + item.route, {
        waitUntil: "domcontentloaded",
        timeout: 20_000,
      });
      await page.waitForTimeout(1200);
      urlsHere = await extractRoutesFromDom(page, baseUrl, pathPrefix);
    } catch (e) {
      log.debug("crawl_failed_route", { route: item.route, error: String(e) });
      continue;
    }

    for (const r of urlsHere) {
      if (!found.has(r)) {
        found.add(r);
        if (item.level < depth && !visited.has(r)) {
          queue.push({ route: r, level: item.level + 1 });
        }
      }
      if (found.size >= maxRoutes) break;
    }
  }

  const sorted = [...found].sort();
  log.info("routes_discovered_dom", {
    total: sorted.length,
    depth,
    visitedCount: visited.size,
  });
  return sorted;
}

async function extractRoutesFromDom(
  page: Page,
  baseUrl: string,
  pathPrefix: string,
): Promise<string[]> {
  return page.evaluate(({ origin, prefix }) => {
    const found = new Set<string>();
    const candidates: HTMLElement[] = [];

    document.querySelectorAll("a[href]").forEach((a) => {
      candidates.push(a as HTMLElement);
    });
    document
      .querySelectorAll("[routerLink], [data-routerlink], [routerlink]")
      .forEach((el) => candidates.push(el as HTMLElement));
    // Tabs PrimeNG (p-tabview, p-tabpanel) frequentemente têm role="tab"
    document
      .querySelectorAll("[role='tab'][data-routerlink]")
      .forEach((el) => candidates.push(el as HTMLElement));

    for (const el of candidates) {
      const raw =
        el.getAttribute("href") ||
        el.getAttribute("routerLink") ||
        el.getAttribute("routerlink") ||
        el.getAttribute("data-routerlink") ||
        "";
      if (!raw) continue;
      try {
        const url = new URL(raw, origin);
        if (url.origin !== origin) continue;
        let p = url.pathname;
        p = p.replace(/\/+$/, "") || "/";
        if (!p.startsWith(prefix)) continue;
        // Descarta IDs numéricos UUIDs e similar
        if (/\/\d+(\/|$)/.test(p)) continue;
        if (
          /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\/|$)/.test(
            p,
          )
        )
          continue;
        found.add(p);
      } catch {
        /* href inválido — ignora */
      }
    }
    return [...found];
  }, { origin: baseUrl, prefix: pathPrefix });
}

// Versão legacy mantida pra retrocompat — chama a nova com depth=1
export async function discoverRoutesShallow(
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
  log.info("routes_discovered_dom_shallow", {
    total: sorted.length,
    seedRoute,
  });
  return sorted;
}
