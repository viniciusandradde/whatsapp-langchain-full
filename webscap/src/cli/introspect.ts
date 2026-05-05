/**
 * CLI: npm run introspect
 *
 * Roda introspection contra o alvo, gera schema.json + schema.graphql
 * SDL no run timestamped. Reusa storageState pra autenticar.
 */

import fs from "node:fs";

import { chromium } from "playwright";

import { ensureStorageFileExists, checkSession } from "../auth/session-guard.js";
import { runIntrospection } from "../graphql/introspect.js";
import { formatSdl } from "../graphql/sdl-formatter.js";
import { log } from "../lib/logger.js";
import {
  createRunPaths,
  updateLatestSymlink,
} from "../lib/output-paths.js";
import { DEFAULT_CONFIG } from "../types.js";

const config = {
  ...DEFAULT_CONFIG,
  baseUrl: process.env["BASE_URL"] ?? DEFAULT_CONFIG.baseUrl,
  authStorageFile:
    process.env["AUTH_FILE"] ?? DEFAULT_CONFIG.authStorageFile,
  outputDir: process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir,
  graphqlPath: process.env["GQL_PATH"] ?? DEFAULT_CONFIG.graphqlPath,
};

ensureStorageFileExists(config.authStorageFile);
const paths = createRunPaths(config.outputDir);

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  storageState: config.authStorageFile,
});
const page = await ctx.newPage();

try {
  // Health check antes de gastar tempo
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

  // Navegação inicial pro contexto da fetch resolver cookies
  await page.goto(config.baseUrl + "/dashboard", {
    waitUntil: "domcontentloaded",
    timeout: config.navTimeoutMs,
  });

  log.info("introspection_starting", { graphql: config.graphqlPath });
  const schema = await runIntrospection(page, config.graphqlPath);

  fs.writeFileSync(paths.schemaJson, JSON.stringify(schema, null, 2));
  log.info("schema_json_written", {
    file: paths.schemaJson,
    types: schema.data!.__schema.types.length,
  });

  const sdl = formatSdl(schema.data!.__schema);
  fs.writeFileSync(paths.schemaSdl, sdl);
  log.info("schema_sdl_written", {
    file: paths.schemaSdl,
    sizeKb: (sdl.length / 1024).toFixed(1),
  });

  updateLatestSymlink(config.outputDir, paths.runDir);
  console.log(`\n✓ Run ${paths.runId}`);
  console.log(`  ${paths.schemaJson}`);
  console.log(`  ${paths.schemaSdl}\n`);
} finally {
  await browser.close();
}
