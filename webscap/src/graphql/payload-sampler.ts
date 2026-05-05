/**
 * Salva 1 exemplo real de payload (variables + response keys) por
 * operation deduped. Útil pra desenhar mocks/tests no Nexus depois.
 */

import fs from "node:fs";
import path from "node:path";

import type { DedupedOperation } from "../types.js";

export function savePayloadSamples(
  ops: DedupedOperation[],
  outDir: string,
): number {
  fs.mkdirSync(outDir, { recursive: true });
  let saved = 0;
  for (const op of ops) {
    if (!op.sampleVariables && (!op.sampleResponseKeys || op.sampleResponseKeys.length === 0)) continue;
    const file = path.join(outDir, `${sanitize(op.operationName)}.json`);
    fs.writeFileSync(
      file,
      JSON.stringify(
        {
          operationName: op.operationName,
          category: op.category,
          occurrences: op.occurrences,
          variables: op.sampleVariables ?? null,
          responseKeys: op.sampleResponseKeys ?? [],
        },
        null,
        2,
      ),
    );
    saved += 1;
  }
  return saved;
}

function sanitize(name: string): string {
  return name.replace(/[^A-Za-z0-9_-]/g, "_");
}
