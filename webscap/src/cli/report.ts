/**
 * CLI: npm run report
 *
 * Gera inventory.md + report.html consolidando:
 * - schema (run latest)
 * - operations (run latest)
 * - coverage.md (output/coverage.md)
 * - components.md (se houver)
 *
 * Saída em output/latest/ (mesmo run da última capture).
 */

import fs from "node:fs";
import path from "node:path";

import { findLatestRunDir } from "../lib/output-paths.js";
import { renderHtmlReport } from "../reporting/html-report.js";
import { renderInventoryMd } from "../reporting/inventory-md.js";
import {
  DEFAULT_CONFIG,
  type CaptureInventory,
  type CoverageReport,
  type IntrospectionResponse,
} from "../types.js";

const outputDir = process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir;
const runDir = findLatestRunDir(outputDir);
if (!runDir) {
  console.error(`✗ Sem runs em ${outputDir}/runs/. Rode 'npm run capture' primeiro.`);
  process.exit(1);
}

function loadJson<T>(file: string): T | null {
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

const capture = loadJson<CaptureInventory>(path.join(runDir, "routes.json"));
const schema = loadJson<IntrospectionResponse>(
  path.join(runDir, "schema.json"),
);

if (!capture) {
  console.error(`✗ ${runDir}/routes.json não existe. Rode 'npm run capture'.`);
  process.exit(1);
}

// Coverage: tenta carregar JSON estruturado primeiro, cai pra null se só MD
const coverage: CoverageReport | null = (() => {
  // Não temos serialização estruturada do coverage hoje; renderiza MD apenas.
  // No HTML report, mostra com null e cai pro caso "sem dados".
  return null;
})();

// inventory.md
const componentsPath = path.join(runDir, "components.md");
const coveragePath = path.join(outputDir, "coverage.md");
const invMd = renderInventoryMd(capture, runDir, {
  coveragePath: fs.existsSync(coveragePath) ? coveragePath : undefined,
  componentsPath: fs.existsSync(componentsPath) ? componentsPath : undefined,
});
const invMdFile = path.join(runDir, "inventory.md");
fs.writeFileSync(invMdFile, invMd);

// report.html
const reportHtml = renderHtmlReport({
  capture,
  schema: schema?.data?.__schema ?? null,
  coverage,
  runDir,
});
const reportHtmlFile = path.join(runDir, "report.html");
fs.writeFileSync(reportHtmlFile, reportHtml);

console.log(`\n✓ ${invMdFile}`);
console.log(`✓ ${reportHtmlFile}`);
console.log(`  Abra o HTML no browser: file://${reportHtmlFile}\n`);
