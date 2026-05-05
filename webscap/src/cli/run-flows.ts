/**
 * CLI: npm run flows
 *
 * Carrega todos os YAMLs em ./flows/, executa em sequência. Output
 * vai pro run timestamped junto com schemas/captures.
 */

import fs from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import {
  checkSession,
  ensureStorageFileExists,
} from "../auth/session-guard.js";
import { parseYamlFile } from "../flows/yaml-loader.js";
import { runFlow } from "../flows/runner.js";
import { log } from "../lib/logger.js";
import {
  createRunPaths,
  findLatestRunDir,
  updateLatestSymlink,
} from "../lib/output-paths.js";
import type { FlowDefinition, FlowResult } from "../flows/types.js";
import { DEFAULT_CONFIG } from "../types.js";

const config = {
  ...DEFAULT_CONFIG,
  baseUrl: process.env["BASE_URL"] ?? DEFAULT_CONFIG.baseUrl,
  authStorageFile:
    process.env["AUTH_FILE"] ?? DEFAULT_CONFIG.authStorageFile,
  outputDir: process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir,
  graphqlPath: process.env["GQL_PATH"] ?? DEFAULT_CONFIG.graphqlPath,
};
const flowsDir = process.env["FLOWS_DIR"] ?? "flows";
const onlyTagsRaw = process.env["ONLY_TAGS"] ?? "";
const onlyTags = onlyTagsRaw
  ? new Set(onlyTagsRaw.split(",").map((t) => t.trim()))
  : null;

ensureStorageFileExists(config.authStorageFile);
if (!fs.existsSync(flowsDir)) {
  console.error(`\n✗ Diretório ${flowsDir} não existe. Crie YAMLs primeiro.\n`);
  process.exit(1);
}

const flowFiles = fs
  .readdirSync(flowsDir)
  .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"))
  .map((f) => path.join(flowsDir, f));

if (flowFiles.length === 0) {
  console.error(`\n✗ Nenhum *.yaml em ${flowsDir}/.\n`);
  process.exit(1);
}

// Flows reusa o run latest se existir (pra coverage/report ver tudo
// junto); cria novo só se for primeira execução. Permite `npm run
// all:full` produzir 1 único run consolidado.
const reuseLatest = process.env["REUSE_LATEST_RUN"] !== "false";
const latestExisting = reuseLatest ? findLatestRunDir(config.outputDir) : null;
const paths = latestExisting
  ? {
      runId: path.basename(latestExisting),
      runDir: latestExisting,
      schemaJson: path.join(latestExisting, "schema.json"),
      schemaSdl: path.join(latestExisting, "schema.graphql"),
      operationsJson: path.join(latestExisting, "operations.json"),
      payloadsDir: path.join(latestExisting, "payloads"),
      routesJson: path.join(latestExisting, "routes.json"),
      screenshotsDir: path.join(latestExisting, "screenshots"),
      harDir: path.join(latestExisting, "har"),
      reportHtml: path.join(latestExisting, "report.html"),
    }
  : createRunPaths(config.outputDir);

// Garante dirs (caso reuse de run que não tinha esses)
fs.mkdirSync(paths.payloadsDir, { recursive: true });
fs.mkdirSync(paths.screenshotsDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  storageState: config.authStorageFile,
});
const page = await ctx.newPage();

try {
  const status = await checkSession(page, {
    baseUrl: config.baseUrl,
    graphqlPath: config.baseUrl + config.graphqlPath,
    storageFile: config.authStorageFile,
  });
  if (!status.alive) {
    log.error("session_dead", { reason: status.reason });
    process.exit(2);
  }

  const results: FlowResult[] = [];
  for (const file of flowFiles) {
    const def = parseYamlFile(file) as FlowDefinition;
    if (!def.name || !Array.isArray(def.steps)) {
      log.warn("flow_invalid", { file });
      continue;
    }
    if (onlyTags && !(def.tags ?? []).some((t) => onlyTags.has(t))) {
      log.debug("flow_skipped_tags", { name: def.name });
      continue;
    }
    log.info("flow_starting", { name: def.name, steps: def.steps.length });
    const r = await runFlow(def, {
      page,
      baseUrl: config.baseUrl,
      screenshotsDir: paths.screenshotsDir,
      payloadsDir: paths.payloadsDir,
      graphqlPath: config.graphqlPath,
    });
    results.push(r);
    if (r.ok) {
      log.info("flow_done", {
        name: r.name,
        steps: `${r.stepsRun}/${r.stepsTotal}`,
        durationMs: r.durationMs,
        payloads: r.payloadsCaptured.length,
        screenshots: r.screenshotsCaptured.length,
      });
    } else {
      log.error("flow_failed", {
        name: r.name,
        atStep: r.errorAtStep,
        error: r.errorMessage,
      });
    }
  }

  fs.writeFileSync(
    path.join(paths.runDir, "flows-results.json"),
    JSON.stringify(results, null, 2),
  );
  updateLatestSymlink(config.outputDir, paths.runDir);

  const okCount = results.filter((r) => r.ok).length;
  console.log(`\n✓ Run ${paths.runId}`);
  console.log(`  ${results.length} flows: ${okCount} ok / ${results.length - okCount} falha`);
  console.log(`  ${paths.runDir}\n`);

  if (okCount < results.length) process.exit(1);
} finally {
  await ctx.close();
  await browser.close();
}
