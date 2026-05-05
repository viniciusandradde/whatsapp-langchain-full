/**
 * CLI: npm run diff:visual
 *
 * Compara screenshots baseline com latest, gera diff PNG por imagem
 * que mudou + visual-diff.md.
 */

import fs from "node:fs";
import path from "node:path";

import { findLatestRunDir } from "../lib/output-paths.js";
import { diffAllScreenshots, renderVisualDiffMd } from "../ui/visual-diff.js";
import { DEFAULT_CONFIG } from "../types.js";

const outputDir = process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir;
const baselineDir = path.join(outputDir, "baseline", "screenshots");
const latest = findLatestRunDir(outputDir);

if (!latest) {
  console.error("✗ Sem runs.");
  process.exit(1);
}
if (!fs.existsSync(baselineDir)) {
  console.error(`✗ Sem baseline em ${baselineDir}. Rode 'npm run baseline'.`);
  process.exit(1);
}

const currentDir = path.join(latest, "screenshots");
const diffOut = path.join(latest, "diff-images");

const summary = diffAllScreenshots({
  baselineDir,
  currentDir,
  outDir: diffOut,
});

const md = renderVisualDiffMd(summary);
const mdFile = path.join(outputDir, "visual-diff.md");
fs.writeFileSync(mdFile, md);

console.log(`\n✓ ${mdFile}`);
console.log(
  `  ${summary.summary.matched} match · ${summary.summary.diff} diff · ${summary.summary.missing} missing`,
);
if (summary.summary.diff > 0) {
  console.log(`  Diffs em ${diffOut}/\n`);
}
