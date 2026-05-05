/**
 * Layout de output:
 *
 *   output/
 *     runs/
 *       2026-05-05_180000/
 *         schema.graphql
 *         schema.json
 *         operations.json
 *         payloads/<op>.json
 *         routes.json
 *         screenshots/
 *         har/<route>.har
 *         report.html
 *     latest -> runs/2026-05-05_180000   (symlink, atualizado a cada run)
 *     baseline/                          (snapshot promovido manualmente)
 *     coverage.md                        (sempre regenerado pra latest)
 *
 * Cada run timestamped preserva histórico — diff entre runs vira F3.
 */

import fs from "node:fs";
import path from "node:path";

import { log } from "./logger.js";

export interface RunPaths {
  runId: string;
  runDir: string;
  schemaJson: string;
  schemaSdl: string;
  operationsJson: string;
  payloadsDir: string;
  routesJson: string;
  screenshotsDir: string;
  harDir: string;
  reportHtml: string;
}

function timestamp(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  );
}

export function createRunPaths(outputDir: string): RunPaths {
  const runId = timestamp();
  const runDir = path.join(outputDir, "runs", runId);
  const paths: RunPaths = {
    runId,
    runDir,
    schemaJson: path.join(runDir, "schema.json"),
    schemaSdl: path.join(runDir, "schema.graphql"),
    operationsJson: path.join(runDir, "operations.json"),
    payloadsDir: path.join(runDir, "payloads"),
    routesJson: path.join(runDir, "routes.json"),
    screenshotsDir: path.join(runDir, "screenshots"),
    harDir: path.join(runDir, "har"),
    reportHtml: path.join(runDir, "report.html"),
  };

  for (const dir of [
    runDir,
    paths.payloadsDir,
    paths.screenshotsDir,
    paths.harDir,
  ]) {
    fs.mkdirSync(dir, { recursive: true });
  }

  return paths;
}

/** Atualiza output/latest pra apontar pro último run. */
export function updateLatestSymlink(outputDir: string, runDir: string): void {
  const latest = path.join(outputDir, "latest");
  try {
    if (fs.existsSync(latest) || fs.lstatSync(latest, { throwIfNoEntry: false })) {
      fs.rmSync(latest, { force: true, recursive: false });
    }
  } catch {
    /* ignora */
  }
  try {
    // relative symlink — funciona em git e em docker mounts
    const target = path.relative(outputDir, runDir);
    fs.symlinkSync(target, latest, "dir");
    log.debug("latest_symlink_updated", { target });
  } catch (e) {
    // Windows sem perms ou FS sem symlink: cai pra arquivo .latest com o path
    const fallback = path.join(outputDir, ".latest");
    fs.writeFileSync(fallback, runDir);
    log.warn("symlink_failed_fallback_file", { fallback, error: String(e) });
  }
}

/** Resolve o run mais recente pra reuso por outros comandos. */
export function findLatestRunDir(outputDir: string): string | null {
  const latest = path.join(outputDir, "latest");
  if (fs.existsSync(latest)) {
    const stat = fs.lstatSync(latest);
    if (stat.isSymbolicLink()) {
      return path.resolve(outputDir, fs.readlinkSync(latest));
    }
  }
  const fallback = path.join(outputDir, ".latest");
  if (fs.existsSync(fallback)) {
    return fs.readFileSync(fallback, "utf8").trim();
  }
  // Último recurso: pega diretório lexicograficamente maior em runs/
  const runsDir = path.join(outputDir, "runs");
  if (!fs.existsSync(runsDir)) return null;
  const entries = fs
    .readdirSync(runsDir)
    .filter((e) => fs.statSync(path.join(runsDir, e)).isDirectory())
    .sort()
    .reverse();
  return entries.length > 0 ? path.join(runsDir, entries[0]!) : null;
}
