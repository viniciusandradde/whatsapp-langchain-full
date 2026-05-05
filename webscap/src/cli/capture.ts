/**
 * CLI: npm run capture
 *
 * Visita rotas (estáticas ou descobertas) com retry + rate limit,
 * intercepta GraphQL, dedupe operations, salva payload samples,
 * tira screenshot e exporta HAR por rota.
 */

import fs from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import {
  checkSession,
  ensureStorageFileExists,
} from "../auth/session-guard.js";
import {
  discoverRoutes,
  STATIC_ROUTES_FALLBACK,
} from "../crawler/route-discovery.js";
import { dedupe } from "../graphql/operation-collector.js";
import { savePayloadSamples } from "../graphql/payload-sampler.js";
import { log } from "../lib/logger.js";
import {
  createRunPaths,
  updateLatestSymlink,
} from "../lib/output-paths.js";
import { withRetry } from "../lib/retry.js";
import { attachGraphqlInterceptor } from "../network/interceptor.js";
import { rateLimiter } from "../network/rate-limiter.js";
import {
  DEFAULT_CONFIG,
  type CaptureInventory,
  type RouteVisit,
} from "../types.js";

const config = {
  ...DEFAULT_CONFIG,
  baseUrl: process.env["BASE_URL"] ?? DEFAULT_CONFIG.baseUrl,
  authStorageFile:
    process.env["AUTH_FILE"] ?? DEFAULT_CONFIG.authStorageFile,
  outputDir: process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir,
  graphqlPath: process.env["GQL_PATH"] ?? DEFAULT_CONFIG.graphqlPath,
};
const enableHar = process.env["ENABLE_HAR"] === "true";
const enableDiscovery = process.env["DISCOVER_ROUTES"] !== "false";

ensureStorageFileExists(config.authStorageFile);
const paths = createRunPaths(config.outputDir);

const browser = await chromium.launch({ headless: true });

async function withHarCtx() {
  return browser.newContext({
    storageState: config.authStorageFile,
    recordHar: enableHar
      ? {
          path: path.join(paths.harDir, "session.har"),
          mode: "minimal",
        }
      : undefined,
  });
}

const ctx = await withHarCtx();
const page = await ctx.newPage();

try {
  const status = await checkSession(page, {
    baseUrl: config.baseUrl,
    graphqlPath: config.baseUrl + config.graphqlPath,
    storageFile: config.authStorageFile,
  });
  if (!status.alive) {
    log.error("session_dead", { reason: status.reason });
    console.error(
      `\n✗ Sessão expirou. Rode 'npm run login' pra renovar.\n  Motivo: ${status.reason}\n`,
    );
    process.exit(2);
  }
  log.info("session_alive");

  // Descoberta de rotas (default true; cai pro fallback se discovery falhar)
  let routes: string[];
  if (enableDiscovery) {
    try {
      const discovered = await discoverRoutes(page, config.baseUrl);
      routes = discovered.length > 0 ? discovered : STATIC_ROUTES_FALLBACK;
      log.info("routes_discovered", { count: routes.length });
    } catch (e) {
      log.warn("discovery_failed_using_fallback", { error: String(e) });
      routes = STATIC_ROUTES_FALLBACK;
    }
  } else {
    routes = STATIC_ROUTES_FALLBACK;
    log.info("routes_static", { count: routes.length });
  }

  const interceptor = attachGraphqlInterceptor(page, {
    graphqlPath: config.graphqlPath,
  });

  const limiter = rateLimiter(config.rateLimitRps);
  const visits: RouteVisit[] = [];

  for (const route of routes) {
    await limiter.acquire();
    const visit = await visitRoute(page, route);
    visits.push(visit);
  }

  // Dedupe + payload samples
  const deduped = dedupe(interceptor.operations);
  log.info("operations_deduped", {
    raw: interceptor.operations.length,
    unique: deduped.length,
  });
  const savedSamples = savePayloadSamples(deduped, paths.payloadsDir);
  log.info("payload_samples_saved", { count: savedSamples });

  // Inventory
  const inventory: CaptureInventory = {
    baseUrl: config.baseUrl,
    capturedAt: new Date().toISOString(),
    routes: visits,
    operations: deduped,
  };
  fs.writeFileSync(
    paths.operationsJson,
    JSON.stringify(deduped, null, 2),
  );
  fs.writeFileSync(paths.routesJson, JSON.stringify(inventory, null, 2));

  updateLatestSymlink(config.outputDir, paths.runDir);
  console.log(`\n✓ Run ${paths.runId}`);
  console.log(`  ${routes.length} rotas (${visits.filter((v) => v.ok).length} ok)`);
  console.log(`  ${deduped.length} operations únicas`);
  console.log(`  ${savedSamples} payload samples`);
  console.log(`  ${paths.runDir}\n`);
} finally {
  // Importante fechar o context pra HAR ser flushed
  await ctx.close();
  await browser.close();
}

async function visitRoute(
  page: import("playwright").Page,
  route: string,
): Promise<RouteVisit> {
  const url = config.baseUrl + route;
  const safeName = route.replace(/[^A-Za-z0-9_-]+/g, "_") || "root";
  const screenshotFile = path.join(paths.screenshotsDir, `${safeName}.png`);
  const startedAt = Date.now();

  try {
    await withRetry(
      async () => {
        const resp = await page.goto(url, {
          waitUntil: "networkidle",
          timeout: config.navTimeoutMs,
        });
        if (resp && !resp.ok()) {
          const err = new Error(`HTTP ${resp.status()}`);
          (err as { status?: number }).status = resp.status();
          throw err;
        }
      },
      {
        maxAttempts: config.retryMaxAttempts,
        baseMs: config.retryBaseMs,
      },
      `goto ${route}`,
    );

    // Pequena pausa pra apps Angular/React flushiarem operations finais
    await page.waitForTimeout(800);

    try {
      await page.screenshot({ path: screenshotFile, fullPage: true });
    } catch (e) {
      log.warn("screenshot_failed", { route, error: String(e) });
    }

    const visit: RouteVisit = {
      url,
      finalUrl: page.url(),
      ok: true,
      loadMs: Date.now() - startedAt,
      screenshotPath: screenshotFile,
      capturedAt: new Date().toISOString(),
    };
    log.info("route_ok", {
      route,
      loadMs: visit.loadMs,
      finalUrl: visit.finalUrl,
    });
    return visit;
  } catch (e) {
    log.error("route_failed", { route, error: String(e) });
    return {
      url,
      finalUrl: page.url(),
      ok: false,
      errorMessage: String(e).slice(0, 200),
      loadMs: Date.now() - startedAt,
      capturedAt: new Date().toISOString(),
    };
  }
}
