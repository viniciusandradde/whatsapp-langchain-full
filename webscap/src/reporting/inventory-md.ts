/**
 * Inventory.md navegável: TOC + índice por entidade + screenshots inline
 * (relativos pra abrir diretamente no GitHub/VSCode).
 */

import path from "node:path";

import type {
  CaptureInventory,
  DedupedOperation,
  RouteVisit,
} from "../types.js";

export function renderInventoryMd(
  inv: CaptureInventory,
  runDir: string,
  options: { coveragePath?: string; componentsPath?: string } = {},
): string {
  const lines: string[] = [];

  lines.push("# Inventory ZigChat — capturado " + inv.capturedAt);
  lines.push("");
  lines.push(`Base URL: \`${inv.baseUrl}\``);
  lines.push(`Run dir: \`${path.basename(runDir)}\``);
  lines.push("");

  // TOC
  lines.push("## Índice");
  lines.push("");
  lines.push("- [Resumo](#resumo)");
  lines.push("- [Rotas visitadas](#rotas-visitadas)");
  lines.push("- [Operations por categoria](#operations-por-categoria)");
  if (options.coveragePath) {
    lines.push(`- [Coverage report](${rel(runDir, options.coveragePath)})`);
  }
  if (options.componentsPath) {
    lines.push(`- [Components PrimeNG](${rel(runDir, options.componentsPath)})`);
  }
  lines.push("- [Screenshots](#screenshots)");
  lines.push("");

  // Resumo
  lines.push("## Resumo");
  lines.push("");
  lines.push(`- **${inv.routes.length}** rotas visitadas (${inv.routes.filter((r) => r.ok).length} OK)`);
  lines.push(`- **${inv.operations.length}** operations únicas capturadas`);
  const totalOcc = inv.operations.reduce((s, o) => s + o.occurrences, 0);
  lines.push(`- **${totalOcc}** chamadas GraphQL totais (deduplicated)`);
  lines.push("");

  // Rotas
  lines.push("## Rotas visitadas");
  lines.push("");
  lines.push("| Rota | Status | Load | Final URL |");
  lines.push("|---|---|---|---|");
  for (const r of inv.routes) {
    const icon = r.ok ? "✅" : "❌";
    const load = r.loadMs ? `${r.loadMs}ms` : "—";
    lines.push(
      `| \`${pathOnly(r.url)}\` | ${icon} | ${load} | \`${pathOnly(r.finalUrl)}\` |`,
    );
  }
  lines.push("");

  // Operations por categoria
  lines.push("## Operations por categoria");
  lines.push("");
  const byCat = new Map<string, DedupedOperation[]>();
  for (const op of inv.operations) {
    const arr = byCat.get(op.category) ?? [];
    arr.push(op);
    byCat.set(op.category, arr);
  }
  const sortedCats = [...byCat.entries()].sort(
    (a, b) => b[1].length - a[1].length,
  );
  for (const [cat, ops] of sortedCats) {
    lines.push(`### \`${cat}\` (${ops.length} op${ops.length > 1 ? "s" : ""})`);
    lines.push("");
    for (const op of ops) {
      const routes = op.routes.map((r) => `\`${pathOnly(r)}\``).join(", ");
      lines.push(
        `- **\`${op.operationName}\`** — ${op.occurrences}× em ${routes}`,
      );
    }
    lines.push("");
  }

  // Screenshots
  lines.push("## Screenshots");
  lines.push("");
  for (const r of inv.routes) {
    if (!r.screenshotPath) continue;
    const sp = rel(runDir, r.screenshotPath);
    lines.push(`### \`${pathOnly(r.url)}\``);
    lines.push("");
    lines.push(`![${pathOnly(r.url)}](${sp})`);
    lines.push("");
  }

  return lines.join("\n");
}

function pathOnly(url: string): string {
  try {
    return new URL(url).pathname || url;
  } catch {
    return url;
  }
}

function rel(from: string, to: string): string {
  return path.relative(from, to) || to;
}
