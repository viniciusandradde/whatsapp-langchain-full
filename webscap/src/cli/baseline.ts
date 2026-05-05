/**
 * CLI: npm run baseline
 *
 * Promove screenshots + schema do run latest pra `output/baseline/`,
 * pra servir de referência em diffs futuros.
 */

import fs from "node:fs";
import path from "node:path";

import { findLatestRunDir } from "../lib/output-paths.js";
import { DEFAULT_CONFIG } from "../types.js";

const outputDir = process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir;
const latest = findLatestRunDir(outputDir);
if (!latest) {
  console.error(`✗ Sem runs em ${outputDir}/runs/.`);
  process.exit(1);
}

const baselineDir = path.join(outputDir, "baseline");
fs.rmSync(baselineDir, { recursive: true, force: true });
fs.mkdirSync(baselineDir, { recursive: true });

// Copia screenshots
const screensSrc = path.join(latest, "screenshots");
if (fs.existsSync(screensSrc)) {
  const dest = path.join(baselineDir, "screenshots");
  fs.mkdirSync(dest, { recursive: true });
  for (const f of fs.readdirSync(screensSrc)) {
    fs.copyFileSync(path.join(screensSrc, f), path.join(dest, f));
  }
  console.log(`✓ Copiou ${fs.readdirSync(screensSrc).length} screenshots`);
}

// Copia schema.json
const schemaSrc = path.join(latest, "schema.json");
if (fs.existsSync(schemaSrc)) {
  fs.copyFileSync(schemaSrc, path.join(baselineDir, "schema.json"));
  console.log(`✓ schema.json copiado`);
}

// Marca origem
fs.writeFileSync(
  path.join(baselineDir, "origin.txt"),
  `Promovido de ${latest} em ${new Date().toISOString()}\n`,
);

console.log(`\n✓ Baseline em ${baselineDir}`);
