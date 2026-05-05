/**
 * CLI: npm run coverage
 *
 * Lê operations.json do último run, lê db/migrations/*.sql do Nexus,
 * gera coverage.md em output/.
 */

import fs from "node:fs";
import path from "node:path";

import { log } from "../lib/logger.js";
import { findLatestRunDir } from "../lib/output-paths.js";
import {
  buildCoverage,
  loadNexusEntities,
  renderCoverageMarkdown,
} from "../reporting/coverage-report.js";
import {
  DEFAULT_CONFIG,
  type DedupedOperation,
} from "../types.js";

const outputDir = process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir;
// Default: 2 níveis acima do webscap/ pra apontar pra db/migrations/ do
// repo principal. Override via env.
const migrationsDir =
  process.env["NEXUS_MIGRATIONS_DIR"] ??
  path.resolve("..", "db", "migrations");

const latestRun = findLatestRunDir(outputDir);
if (!latestRun) {
  console.error(
    `\n✗ Sem runs anteriores em ${outputDir}/runs/. Rode 'npm run capture' primeiro.\n`,
  );
  process.exit(1);
}

const opsFile = path.join(latestRun, "operations.json");
if (!fs.existsSync(opsFile)) {
  console.error(`\n✗ ${opsFile} não existe. Rode 'npm run capture' primeiro.\n`);
  process.exit(1);
}

const ops = JSON.parse(fs.readFileSync(opsFile, "utf8")) as DedupedOperation[];
log.info("coverage_loading", { ops: ops.length, latestRun });

const entities = loadNexusEntities(migrationsDir);
log.info("nexus_entities_loaded", {
  count: entities.length,
  sample: entities.slice(0, 5).map((e) => e.name),
});

const report = buildCoverage(ops, entities, latestRun, migrationsDir);
const md = renderCoverageMarkdown(report);

const outFile = path.join(outputDir, "coverage.md");
fs.writeFileSync(outFile, md);
console.log(`\n✓ ${outFile}`);
console.log(
  `  ${report.summary.totalCategories} categorias: ` +
    `${report.summary.covered} covered, ` +
    `${report.summary.partial} partial, ` +
    `${report.summary.missing} missing\n`,
);
