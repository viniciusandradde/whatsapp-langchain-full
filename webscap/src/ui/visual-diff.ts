/**
 * Visual diff entre 2 PNGs com pixelmatch — detecta redesigns/regressões
 * visuais entre runs.
 *
 * Workflow:
 * 1. `npm run baseline` — promove screenshots do run latest pra `output/baseline/`
 * 2. ZigChat redesigna (futuramente) → run novo gera screenshots diferentes
 * 3. `npm run diff:visual` — compara cada screenshot baseline vs latest,
 *     gera PNG do diff em vermelho + relatório com % mudança
 *
 * Threshold default 0.1 (10% diff = mudou pra valer; menos é flake render).
 */

import fs from "node:fs";
import path from "node:path";

import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

export interface VisualDiffResult {
  filename: string;
  status: "match" | "diff" | "missing-baseline" | "missing-current" | "size-mismatch";
  /** Pixels diferentes (após threshold). */
  diffPixels?: number;
  /** Total de pixels da imagem. */
  totalPixels?: number;
  /** % diff (0-100). */
  diffPercent?: number;
  /** Path onde salvou o PNG do diff (se status=diff). */
  diffImagePath?: string;
}

export interface VisualDiffSummary {
  generatedAt: string;
  baselineDir: string;
  currentDir: string;
  threshold: number;
  results: VisualDiffResult[];
  summary: {
    matched: number;
    diff: number;
    missing: number;
  };
}

export interface DiffOptions {
  baselineDir: string;
  currentDir: string;
  outDir: string;
  /** Pixelmatch threshold 0-1 (0 = sensível, 1 = ignora tudo). Default 0.1. */
  threshold?: number;
  /** % diff acima disso conta como mudança real. Default 0.5%. */
  changeThresholdPercent?: number;
}

export function diffAllScreenshots(opts: DiffOptions): VisualDiffSummary {
  const threshold = opts.threshold ?? 0.1;
  const changeThreshold = opts.changeThresholdPercent ?? 0.5;
  fs.mkdirSync(opts.outDir, { recursive: true });

  const baselineFiles = fs.existsSync(opts.baselineDir)
    ? fs.readdirSync(opts.baselineDir).filter((f) => f.endsWith(".png"))
    : [];
  const currentFiles = fs.existsSync(opts.currentDir)
    ? fs.readdirSync(opts.currentDir).filter((f) => f.endsWith(".png"))
    : [];

  const all = new Set([...baselineFiles, ...currentFiles]);
  const results: VisualDiffResult[] = [];

  for (const file of all) {
    const baselinePath = path.join(opts.baselineDir, file);
    const currentPath = path.join(opts.currentDir, file);

    if (!fs.existsSync(baselinePath)) {
      results.push({ filename: file, status: "missing-baseline" });
      continue;
    }
    if (!fs.existsSync(currentPath)) {
      results.push({ filename: file, status: "missing-current" });
      continue;
    }

    const before = PNG.sync.read(fs.readFileSync(baselinePath));
    const after = PNG.sync.read(fs.readFileSync(currentPath));

    if (before.width !== after.width || before.height !== after.height) {
      results.push({ filename: file, status: "size-mismatch" });
      continue;
    }

    const diff = new PNG({ width: before.width, height: before.height });
    const diffPixels = pixelmatch(
      before.data,
      after.data,
      diff.data,
      before.width,
      before.height,
      { threshold, includeAA: false },
    );
    const total = before.width * before.height;
    const pct = (diffPixels / total) * 100;

    if (pct < changeThreshold) {
      results.push({
        filename: file,
        status: "match",
        diffPixels,
        totalPixels: total,
        diffPercent: pct,
      });
    } else {
      const diffPath = path.join(opts.outDir, file);
      fs.writeFileSync(diffPath, PNG.sync.write(diff));
      results.push({
        filename: file,
        status: "diff",
        diffPixels,
        totalPixels: total,
        diffPercent: pct,
        diffImagePath: diffPath,
      });
    }
  }

  // Ordena por % diff desc
  results.sort((a, b) => (b.diffPercent ?? 0) - (a.diffPercent ?? 0));

  return {
    generatedAt: new Date().toISOString(),
    baselineDir: opts.baselineDir,
    currentDir: opts.currentDir,
    threshold,
    results,
    summary: {
      matched: results.filter((r) => r.status === "match").length,
      diff: results.filter((r) => r.status === "diff").length,
      missing: results.filter(
        (r) => r.status === "missing-baseline" || r.status === "missing-current",
      ).length,
    },
  };
}

export function renderVisualDiffMd(s: VisualDiffSummary): string {
  const lines: string[] = [];
  lines.push("# Visual Diff Report");
  lines.push("");
  lines.push(`> Gerado em ${s.generatedAt}`);
  lines.push(`> Baseline: \`${s.baselineDir}\``);
  lines.push(`> Current: \`${s.currentDir}\``);
  lines.push(`> Threshold: ${s.threshold}`);
  lines.push("");
  lines.push("## Resumo");
  lines.push("");
  lines.push(`- ✅ **${s.summary.matched}** screens batem`);
  lines.push(`- 🔄 **${s.summary.diff}** screens com mudanças`);
  lines.push(`- ❓ **${s.summary.missing}** missing (sem baseline ou sem current)`);
  lines.push("");

  const diffs = s.results.filter((r) => r.status === "diff");
  if (diffs.length > 0) {
    lines.push("## Mudanças detectadas");
    lines.push("");
    lines.push("| Screenshot | % diff | Pixels |");
    lines.push("|---|---|---|");
    for (const r of diffs) {
      lines.push(
        `| \`${r.filename}\` | ${r.diffPercent?.toFixed(2)}% | ${r.diffPixels}/${r.totalPixels} |`,
      );
    }
    lines.push("");
  }

  const missing = s.results.filter(
    (r) => r.status === "missing-baseline" || r.status === "missing-current",
  );
  if (missing.length > 0) {
    lines.push("## Sem par");
    lines.push("");
    for (const r of missing) {
      lines.push(`- ${r.status === "missing-baseline" ? "🆕" : "🗑️"} \`${r.filename}\``);
    }
  }

  return lines.join("\n");
}
