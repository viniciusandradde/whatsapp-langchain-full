/**
 * CLI: npm run diff:schema
 *
 * Compara schema.json do baseline com schema.json do latest.
 * Output: schema-diff.md.
 *
 * Uso:
 *   npm run diff:schema                       # baseline vs latest
 *   BEFORE=output/runs/X AFTER=output/runs/Y npm run diff:schema
 */

import fs from "node:fs";
import path from "node:path";

import { computeSchemaDiff, renderSchemaDiffMarkdown } from "../diff/schema-diff.js";
import { findLatestRunDir } from "../lib/output-paths.js";
import {
  DEFAULT_CONFIG,
  type IntrospectionResponse,
} from "../types.js";

const outputDir = process.env["OUTPUT_DIR"] ?? DEFAULT_CONFIG.outputDir;

function resolveSchemaPath(label: string, override: string | undefined): string {
  if (override) {
    if (override.endsWith(".json")) return override;
    return path.join(override, "schema.json");
  }
  if (label === "before") {
    const baseline = path.join(outputDir, "baseline", "schema.json");
    if (fs.existsSync(baseline)) return baseline;
    throw new Error(
      `Sem baseline. Promova um run: cp ${outputDir}/latest/schema.json ${outputDir}/baseline/schema.json`,
    );
  }
  // after
  const latest = findLatestRunDir(outputDir);
  if (!latest) throw new Error("Sem runs.");
  return path.join(latest, "schema.json");
}

const beforePath = resolveSchemaPath("before", process.env["BEFORE"]);
const afterPath = resolveSchemaPath("after", process.env["AFTER"]);

const beforeJson = JSON.parse(
  fs.readFileSync(beforePath, "utf8"),
) as IntrospectionResponse;
const afterJson = JSON.parse(
  fs.readFileSync(afterPath, "utf8"),
) as IntrospectionResponse;

if (!beforeJson.data?.__schema || !afterJson.data?.__schema) {
  console.error("Schema inválido.");
  process.exit(1);
}

const diff = computeSchemaDiff(
  beforeJson.data.__schema,
  afterJson.data.__schema,
);
const md = renderSchemaDiffMarkdown(diff);

const outFile = path.join(outputDir, "schema-diff.md");
fs.writeFileSync(outFile, md);
console.log(`\n✓ ${outFile}`);
console.log(
  `  +${diff.summary.typesAdded} types  -${diff.summary.typesRemoved} types  ~${diff.summary.typesModified} types  ⚠${diff.summary.breakingChanges} breaking\n`,
);
