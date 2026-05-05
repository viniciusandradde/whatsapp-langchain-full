/**
 * Mini-parser YAML — sem dependência externa pra evitar bloat.
 *
 * Cobre o subset usado pelos flows: scalars (string/number/bool),
 * arrays inline `[a, b]` e block `- item`, mappings `key: value` e
 * block, indentation por espaços (2). Sem anchors, sem multi-doc, sem
 * tags custom.
 *
 * Pra subset maior, trocar por js-yaml. Pra hoje, isso cobre nossos flows.
 */

import fs from "node:fs";

export function parseYamlFile(filePath: string): unknown {
  const content = fs.readFileSync(filePath, "utf8");
  return parseYaml(content);
}

export function parseYaml(text: string): unknown {
  // Remove comentários e linhas vazias
  const lines = text
    .split("\n")
    .map((l) => stripComment(l))
    .filter((l) => l.trim().length > 0 || l.startsWith(" "));

  const ctx = { lines, idx: 0 };
  return parseBlock(ctx, 0);
}

interface Ctx {
  lines: string[];
  idx: number;
}

function stripComment(line: string): string {
  // Remove # comment, exceto dentro de strings
  let inStr = false;
  let out = "";
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') inStr = !inStr;
    if (ch === "#" && !inStr) break;
    out += ch;
  }
  return out.trimEnd();
}

function indent(line: string): number {
  let n = 0;
  while (n < line.length && line[n] === " ") n++;
  return n;
}

function parseBlock(ctx: Ctx, baseIndent: number): unknown {
  if (ctx.idx >= ctx.lines.length) return null;
  const first = ctx.lines[ctx.idx]!;
  const stripped = first.slice(baseIndent);

  if (stripped.startsWith("- ")) {
    return parseList(ctx, baseIndent);
  }
  return parseMap(ctx, baseIndent);
}

function parseMap(ctx: Ctx, baseIndent: number): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  while (ctx.idx < ctx.lines.length) {
    const line = ctx.lines[ctx.idx]!;
    const ind = indent(line);
    if (ind < baseIndent) break;
    if (ind > baseIndent) {
      // Linha mais profunda — pula (já consumida pelo recursive)
      ctx.idx++;
      continue;
    }
    const stripped = line.slice(baseIndent);
    if (stripped.startsWith("- ")) break; // virou lista no mesmo nível

    const colonIdx = stripped.indexOf(":");
    if (colonIdx === -1) {
      ctx.idx++;
      continue;
    }
    const key = stripped.slice(0, colonIdx).trim();
    const valuePart = stripped.slice(colonIdx + 1).trim();
    ctx.idx++;
    if (valuePart === "" || valuePart === "|" || valuePart === ">") {
      // Valor em bloco indentado
      const nextLine = ctx.lines[ctx.idx];
      if (!nextLine) {
        obj[key] = null;
        continue;
      }
      const nextInd = indent(nextLine);
      if (nextInd > baseIndent) {
        obj[key] = parseBlock(ctx, nextInd);
      } else {
        obj[key] = null;
      }
    } else {
      obj[key] = parseScalar(valuePart);
    }
  }
  return obj;
}

function parseList(ctx: Ctx, baseIndent: number): unknown[] {
  const arr: unknown[] = [];
  while (ctx.idx < ctx.lines.length) {
    const line = ctx.lines[ctx.idx]!;
    const ind = indent(line);
    if (ind < baseIndent) break;
    if (ind > baseIndent) {
      ctx.idx++;
      continue;
    }
    const stripped = line.slice(baseIndent);
    if (!stripped.startsWith("- ")) break;
    const itemPart = stripped.slice(2);
    if (itemPart.includes(":")) {
      // Item é um map inline parcial: "- key: value\n  key2: ..."
      // Trata como block: substituímos "- " por "  " e re-parseamos
      ctx.lines[ctx.idx] = " ".repeat(baseIndent + 2) + itemPart;
      arr.push(parseMap(ctx, baseIndent + 2));
    } else {
      ctx.idx++;
      arr.push(parseScalar(itemPart));
    }
  }
  return arr;
}

function parseScalar(s: string): unknown {
  const trimmed = s.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed === "null" || trimmed === "~") return null;
  // Array inline: [a, b, "c"]
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    const inner = trimmed.slice(1, -1);
    if (inner.trim() === "") return [];
    return inner.split(",").map((p) => parseScalar(p.trim()));
  }
  // Number
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  // String com aspas
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}
